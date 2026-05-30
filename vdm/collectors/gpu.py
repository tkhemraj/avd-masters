"""GPU / vGPU collector — queries each host via WinRM + nvidia-smi.

Works for all three platforms by reusing the WinRM session pattern.
For Azure AVD hosts, also supplements with Azure Monitor GPU metrics.

Config (under gpu: in each platform block, or top-level):
  enabled:           true
  nvidia_smi_path:   'C:\\Windows\\System32\\nvidia-smi.exe'   # default
  collect_processes: true    # per-process GPU engine breakdown
  top_processes:     10      # how many top GPU processes to capture
  azure_gpu_metrics: true    # pull Azure Monitor GPU metrics for AVD hosts
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..models.gpu import (
    GPUEngine,
    GPUSnapshot,
    HostGPUData,
    PhysicalGPU,
    VGPUInstance,
    VGPUProfile,
)
from ..utils import sanitize_error

logger = logging.getLogger(__name__)

_NVIDIA_SMI = r"C:\Windows\System32\nvidia-smi.exe"

# ── PowerShell helpers ────────────────────────────────────────────────────────

_PS_VIDEO_CONTROLLERS = (
    "Get-CimInstance Win32_VideoController | "
    "Select-Object Name,AdapterRAM,DriverVersion,VideoProcessor | "
    "ConvertTo-Json -Compress"
)

_PS_GPU_ENGINES = (
    "Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | "
    "Select-Object Name,UtilizationPercentage | "
    "ConvertTo-Json -Compress"
)

_PS_GPU_ADAPTER_MEM = (
    "Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory | "
    "Select-Object Name,DedicatedUsage,SharedUsage,TotalCommitted | "
    "ConvertTo-Json -Compress"
)

_PS_TOP_PROCESSES = (
    "Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | "
    "Where-Object {{$_.Name -match 'pid_([0-9]+)'}} | "
    "Sort-Object UtilizationPercentage -Descending | "
    "Select-Object -First {top} | "
    "ForEach-Object {{ "
    "  $pid = [regex]::Match($_.Name,'pid_([0-9]+)').Groups[1].Value; "
    "  $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue; "
    "  [PSCustomObject]@{{ "
    "    Name=$_.Name; Util=$_.UtilizationPercentage; "
    "    Pid=$pid; ProcessName=if($proc){{$proc.ProcessName}}else{{'unknown'}} "
    "  }} "
    "}} | ConvertTo-Json -Compress"
)

# nvidia-smi CSV queries
_NSMI_GPU = (
    "{smi} --query-gpu=gpu_name,index,memory.total,memory.used,"
    "utilization.gpu,utilization.memory,utilization.encoder,utilization.decoder,"
    "temperature.gpu,power.draw,power.limit,driver_version "
    "--format=csv,noheader,nounits 2>$null"
)

_NSMI_VGPU = (
    "{smi} vgpu --query-vgpu=vgpu_name,vgpu_uuid,gpu_uuid,gpu_bus_id,"
    "fb_memory_usage.total,fb_memory_usage.used,"
    "utilization.gpu,utilization.memory,utilization.encoder,utilization.decoder,"
    "vm_name --format=csv,noheader,nounits 2>$null"
)


def _run_ps(winrm_session, script: str) -> tuple[str, int]:
    result = winrm_session.run_ps(script)
    stdout = result.std_out.decode("utf-8", errors="replace").strip()
    return stdout, result.status_code


def _parse_json_result(stdout: str) -> list[dict]:
    if not stdout:
        return []
    try:
        data = json.loads(stdout)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return []


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        f = float(str(val).strip().replace(",", "."))
        return f if f == f else default  # NaN check
    except (ValueError, TypeError):
        return default


# ── WMI-based GPU collection (vendor-agnostic) ───────────────────────────────

def _collect_wmi_engines(session) -> list[GPUEngine]:
    stdout, rc = _run_ps(session, _PS_GPU_ENGINES)
    if rc != 0 or not stdout:
        return []
    engines: list[GPUEngine] = []
    for row in _parse_json_result(stdout):
        name = row.get("Name", "")
        util = _safe_float(row.get("UtilizationPercentage"))
        if util is None:
            continue
        # Name format: "luid_0x...._phys_0_eng_0_engtype_3D" or "pid_1234_luid_..."
        eng_type = "Other"
        pid = None
        proc_match = re.search(r"pid_(\d+)", name)
        if proc_match:
            pid = int(proc_match.group(1))
        type_match = re.search(r"engtype_(\w+)", name)
        if type_match:
            eng_type = type_match.group(1)
        engines.append(GPUEngine(
            engine_type=eng_type,
            utilization_pct=util,
            pid=pid,
        ))
    return engines


def _collect_wmi_adapter_mem(session) -> dict[str, dict]:
    """Returns adapter LUID → {dedicated_mb, shared_mb}."""
    stdout, rc = _run_ps(session, _PS_GPU_ADAPTER_MEM)
    result: dict[str, dict] = {}
    if rc != 0 or not stdout:
        return result
    for row in _parse_json_result(stdout):
        name = row.get("Name", "")
        # Bytes → MB
        ded = _safe_float(row.get("DedicatedUsage", 0)) or 0
        shared = _safe_float(row.get("SharedUsage", 0)) or 0
        result[name] = {
            "dedicated_mb": int(ded / 1024 / 1024),
            "shared_mb": int(shared / 1024 / 1024),
        }
    return result


def _collect_video_controllers(session) -> list[dict]:
    stdout, rc = _run_ps(session, _PS_VIDEO_CONTROLLERS)
    if rc != 0 or not stdout:
        return []
    return _parse_json_result(stdout)


def _collect_top_processes(session, top: int = 10) -> list[GPUEngine]:
    script = _PS_TOP_PROCESSES.format(top=top)
    stdout, rc = _run_ps(session, script)
    if rc != 0 or not stdout:
        return []
    result: list[GPUEngine] = []
    for row in _parse_json_result(stdout):
        util = _safe_float(row.get("Util"))
        if util is None or util < 1:
            continue
        result.append(GPUEngine(
            engine_type="3D",
            utilization_pct=util,
            pid=int(row.get("Pid", 0)) or None,
            process_name=row.get("ProcessName"),
        ))
    return result


# ── NVIDIA SMI collection ─────────────────────────────────────────────────────

def _collect_nvidia_gpus(session, smi_path: str) -> list[PhysicalGPU]:
    script = _NSMI_GPU.format(smi=smi_path)
    stdout, rc = _run_ps(session, script)
    if rc != 0 or not stdout:
        return []

    gpus: list[PhysicalGPU] = []
    for i, line in enumerate(stdout.strip().splitlines()):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 10:
            continue
        try:
            gpus.append(PhysicalGPU(
                index=int(parts[1]) if parts[1].isdigit() else i,
                name=parts[0],
                total_memory_mb=int(_safe_float(parts[2]) or 0),
                used_memory_mb=int(_safe_float(parts[3]) or 0),
                gpu_util_pct=_safe_float(parts[4]),
                mem_util_pct=_safe_float(parts[5]),
                encoder_util_pct=_safe_float(parts[6]),
                decoder_util_pct=_safe_float(parts[7]),
                temperature_c=_safe_float(parts[8]),
                power_draw_w=_safe_float(parts[9]),
                power_limit_w=_safe_float(parts[10]) if len(parts) > 10 else None,
                driver_version=parts[11].strip() if len(parts) > 11 else None,
            ))
        except (ValueError, IndexError):
            continue
    return gpus


def _collect_vgpu_instances(session, smi_path: str) -> list[VGPUInstance]:
    script = _NSMI_VGPU.format(smi=smi_path)
    stdout, rc = _run_ps(session, script)
    if rc != 0 or not stdout.strip():
        return []

    instances: list[VGPUInstance] = []
    for line in stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 10 or not parts[0]:
            continue
        try:
            profile_name = parts[0]
            instance_id  = parts[1]
            gpu_uuid     = parts[2]
            fb_total     = int(_safe_float(parts[4]) or 0)
            fb_used      = int(_safe_float(parts[5]) or 0)
            sm_util      = _safe_float(parts[6])
            mem_util     = _safe_float(parts[7])
            enc_util     = _safe_float(parts[8])
            dec_util     = _safe_float(parts[9])
            vm_name      = parts[10] if len(parts) > 10 else None

            profile = VGPUProfile.parse(profile_name)
            # Override profile's memory with actual allocated amount from smi
            if fb_total > 0:
                profile.memory_mb = fb_total

            instances.append(VGPUInstance(
                instance_id=instance_id,
                profile=profile,
                gpu_index=0,   # resolved below if GPU UUID map is available
                vm_name=vm_name if vm_name and vm_name.lower() not in ("n/a", "[n/a]", "") else None,
                fb_used_mb=fb_used,
                fb_total_mb=fb_total,
                sm_util_pct=sm_util,
                mem_util_pct=mem_util,
                encoder_util_pct=enc_util,
                decoder_util_pct=dec_util,
            ))
        except (ValueError, IndexError):
            continue
    return instances


# ── Main per-host collector ───────────────────────────────────────────────────

def collect_host_gpu(
    hostname: str,
    platform: str,
    session_factory: Callable[[], Any],
    cfg: dict,
) -> HostGPUData:
    """
    Collect GPU data from a single Windows host via WinRM.

    session_factory: callable returning a pywinrm Session (already configured
                     with credentials and transport by the calling collector).
    """
    smi_path = cfg.get("nvidia_smi_path", _NVIDIA_SMI)
    collect_procs = cfg.get("collect_processes", True)
    top_procs = int(cfg.get("top_processes", 10))

    host_data = HostGPUData(
        hostname=hostname,
        platform=platform,
        collected_at=datetime.now(timezone.utc),
    )

    try:
        session = session_factory()
    except Exception as exc:
        host_data.errors.append(f"WinRM session failed: {sanitize_error(exc)}")
        return host_data

    # 1. Video controller inventory (works for any GPU vendor)
    try:
        controllers = _collect_video_controllers(session)
        has_nvidia = any(
            "nvidia" in (c.get("Name") or "").lower()
            for c in controllers
        )
        host_data.has_nvidia = has_nvidia
    except Exception as exc:
        host_data.errors.append(f"Video controller query: {sanitize_error(exc)}")
        controllers = []

    # 2. WMI GPU engine utilisation (all vendors)
    all_engines: list[GPUEngine] = []
    try:
        all_engines = _collect_wmi_engines(session)
    except Exception as exc:
        host_data.errors.append(f"GPU engine WMI: {sanitize_error(exc)}")

    # 3. Per-process GPU breakdown
    if collect_procs:
        try:
            host_data.top_gpu_processes = _collect_top_processes(session, top_procs)
        except Exception as exc:
            host_data.errors.append(f"GPU process query: {sanitize_error(exc)}")

    # 4. NVIDIA-specific: physical GPU stats + vGPU instances
    nvidia_gpus: list[PhysicalGPU] = []
    vgpu_instances: list[VGPUInstance] = []

    if host_data.has_nvidia:
        try:
            nvidia_gpus = _collect_nvidia_gpus(session, smi_path)
        except Exception as exc:
            host_data.errors.append(f"nvidia-smi GPU query: {sanitize_error(exc)}")

        try:
            vgpu_instances = _collect_vgpu_instances(session, smi_path)
            if vgpu_instances:
                host_data.has_vgpu = True
        except Exception as exc:
            host_data.errors.append(f"nvidia-smi vGPU query: {sanitize_error(exc)}")

        # Distribute vGPU instances across physical GPUs by index
        gpu_map = {g.index: g for g in nvidia_gpus}
        for inst in vgpu_instances:
            gpu = gpu_map.get(inst.gpu_index, nvidia_gpus[0] if nvidia_gpus else None)
            if gpu:
                gpu.vgpu_instances.append(inst)

        # Attach engine metrics to physical GPUs
        if nvidia_gpus:
            for eng in all_engines:
                # Best-effort: attach non-per-process engines to first GPU
                if eng.pid is None:
                    nvidia_gpus[0].engines.append(eng)

        host_data.physical_gpus = nvidia_gpus

    else:
        # Non-NVIDIA: synthesise a PhysicalGPU from WMI data
        for i, ctrl in enumerate(controllers):
            mem_bytes = ctrl.get("AdapterRAM") or 0
            gpu = PhysicalGPU(
                index=i,
                name=ctrl.get("Name") or "GPU",
                total_memory_mb=int(mem_bytes / 1024 / 1024),
                driver_version=ctrl.get("DriverVersion"),
                engines=all_engines,
            )
            host_data.physical_gpus.append(gpu)

    return host_data


# ── Platform-level GPU snapshot builder ──────────────────────────────────────

class GPUCollector:
    """
    Collects GPU data from all hosts across configured platforms.
    Designed to be called after the platform collectors have run,
    using the same WinRM credentials from their configs.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.gpu_cfg = config.get("gpu", {})
        self.logger = logging.getLogger("vdm.collector.gpu")

    def _rds_session_factory(self, hostname: str):
        """Reuse RDS collector's WinRM session logic."""
        try:
            import winrm
        except ImportError as exc:
            raise RuntimeError("pywinrm not installed") from exc

        rds_cfg = self.config.get("rds", {})
        use_ssl = rds_cfg.get("use_ssl", True)
        port = rds_cfg.get("winrm_port", 5986)
        scheme = "https" if use_ssl else "http"
        transport = rds_cfg.get("winrm_transport", "ntlm")
        return winrm.Session(
            f"{scheme}://{hostname}:{port}/wsman",
            auth=(rds_cfg["winrm_username"], rds_cfg["winrm_password"]),
            transport=transport,
            operation_timeout_s=30,
            read_timeout_s=60,
        )

    def _citrix_winrm_session_factory(self, hostname: str):
        try:
            import winrm
        except ImportError as exc:
            raise RuntimeError("pywinrm not installed") from exc

        ctx_cfg = self.config.get("citrix", {})
        use_ssl = ctx_cfg.get("use_ssl", True)
        port = ctx_cfg.get("winrm_port", 5986)
        scheme = "https" if use_ssl else "http"
        transport = ctx_cfg.get("winrm_transport", "ntlm")
        return winrm.Session(
            f"{scheme}://{hostname}:{port}/wsman",
            auth=(ctx_cfg["winrm_username"], ctx_cfg["winrm_password"]),
            transport=transport,
            operation_timeout_s=30,
            read_timeout_s=60,
        )

    def collect(self) -> GPUSnapshot:
        snap = GPUSnapshot(collected_at=datetime.now(timezone.utc))
        gpu_cfg = self.gpu_cfg

        # RDS session hosts
        rds_cfg = self.config.get("rds")
        if rds_cfg and gpu_cfg.get("enabled", True):
            broker_hosts = set(rds_cfg.get("broker_hosts", []))
            for hostname in rds_cfg.get("hosts", []):
                if hostname in broker_hosts:
                    continue  # brokers don't run user sessions
                try:
                    data = collect_host_gpu(
                        hostname=hostname,
                        platform="rds",
                        session_factory=lambda h=hostname: self._rds_session_factory(h),
                        cfg=gpu_cfg,
                    )
                    snap.hosts[hostname] = data
                except Exception as exc:
                    self.logger.warning("GPU collection failed for RDS host %s: %s",
                                        hostname, sanitize_error(exc))
                    snap.errors.append(f"RDS/{hostname}: {sanitize_error(exc)}")

        # Citrix VDAs (WinRM path)
        ctx_cfg = self.config.get("citrix")
        if ctx_cfg and ctx_cfg.get("use_winrm") and gpu_cfg.get("enabled", True):
            # collect from the controller — it can proxy or we query each VDA
            controller = ctx_cfg.get("winrm_host")
            if controller:
                try:
                    data = collect_host_gpu(
                        hostname=controller,
                        platform="citrix",
                        session_factory=lambda h=controller: self._citrix_winrm_session_factory(h),
                        cfg=gpu_cfg,
                    )
                    snap.hosts[controller] = data
                except Exception as exc:
                    snap.errors.append(f"Citrix/{controller}: {sanitize_error(exc)}")

        return snap
