"""Best-practice analysis for GPU / vGPU slices across all platforms.

This is the ROI layer — it tells you whether your vGPU profiles are
correctly sized, whether you're paying for Quadro licences you don't need,
and whether your physical GPUs are earning their keep.
"""

from __future__ import annotations

from typing import Optional

from ..models.gpu import GPUSnapshot, HostGPUData, PhysicalGPU, VGPUInstance
from .base import Category, Finding, Severity

_DEFAULTS = {
    # vGPU slice sizing
    "fb_underused_pct":        20.0,   # FB < 20% used → profile too large
    "fb_saturated_pct":        88.0,   # FB > 88% used → profile too small
    "sm_saturated_pct":        85.0,   # SM (compute) saturation
    "encoder_saturated_pct":   80.0,   # remoting encoder bottleneck
    "sm_q_profile_min_pct":    15.0,   # Q-profile users should use ≥15% SM
                                        # below this → B-profile likely sufficient
    # Physical GPU
    "pgpu_util_warn_pct":      80.0,
    "pgpu_util_crit_pct":      95.0,
    "pgpu_temp_warn_c":        80.0,
    "pgpu_temp_crit_c":        90.0,
    "pgpu_power_warn_pct":     85.0,   # % of power limit
    "pgpu_mem_warn_pct":       85.0,
    # Slice efficiency
    "slice_efficiency_warn_pct": 30.0, # avg FB in use < 30% of allocated = waste
    "min_vgpu_per_pgpu":         1,    # flag pGPU with zero active slices
    # Process GPU hog threshold
    "process_gpu_hog_pct":      60.0,  # single process hogging >60% = flag it
}


def analyse(snap: GPUSnapshot, cfg: Optional[dict] = None) -> list[Finding]:
    t = {**_DEFAULTS, **(cfg or {})}
    findings: list[Finding] = []

    for hostname, host in snap.hosts.items():
        if not host.physical_gpus:
            findings.append(Finding(
                platform=host.platform.upper(), resource=hostname,
                severity=Severity.INFO,
                category=Category.CONFIGURATION,
                title="No GPU detected on host",
                detail=f"{hostname} has no GPU or GPU query failed.",
                recommendation=(
                    "If this host should have GPU acceleration, verify the GPU driver "
                    "is installed and the host is an NV/GPU-series VM or has a physical GPU."
                ),
            ))
            continue

        for gpu in host.physical_gpus:
            _physical_gpu_health(hostname, host.platform, gpu, t, findings)
            if host.has_vgpu and gpu.vgpu_instances:
                _vgpu_slice_sizing(hostname, host.platform, gpu, t, findings)
                _vgpu_profile_licence_check(hostname, host.platform, gpu, t, findings)
                _slice_pack_efficiency(hostname, host.platform, gpu, t, findings)
            elif not host.has_vgpu and host.has_nvidia:
                _full_passthrough_check(hostname, host.platform, gpu, findings)

        if host.top_gpu_processes:
            _gpu_process_hogs(hostname, host.platform, host, t, findings)

    return findings


# ── Physical GPU health ───────────────────────────────────────────────────────

def _physical_gpu_health(hostname, platform, gpu: PhysicalGPU, t, findings):
    label = f"{hostname} / GPU {gpu.index} ({gpu.name})"
    pfx = platform.upper()

    # Overall utilisation
    if gpu.gpu_util_pct is not None:
        if gpu.gpu_util_pct >= t["pgpu_util_crit_pct"]:
            findings.append(Finding(
                platform=pfx, resource=label,
                severity=Severity.CRITICAL,
                category=Category.PERFORMANCE,
                title="Physical GPU critically saturated",
                detail=(
                    f"{gpu.name} on {hostname} is at {gpu.gpu_util_pct:.1f}% utilisation. "
                    "All vGPU slices on this GPU will be contending for compute time."
                ),
                recommendation=(
                    "Reduce the number of vGPU instances on this GPU or migrate some "
                    "instances to a less-loaded physical GPU. "
                    "Review if any VMs are running runaway GPU workloads."
                ),
            ))
        elif gpu.gpu_util_pct >= t["pgpu_util_warn_pct"]:
            findings.append(Finding(
                platform=pfx, resource=label,
                severity=Severity.WARNING,
                category=Category.PERFORMANCE,
                title="Physical GPU utilisation high",
                detail=f"{gpu.name} on {hostname} at {gpu.gpu_util_pct:.1f}%.",
                recommendation=(
                    "Monitor closely. If sustained, consider spreading vGPU instances "
                    "across multiple physical GPUs."
                ),
            ))
        else:
            findings.append(Finding(
                platform=pfx, resource=label,
                severity=Severity.PASS,
                category=Category.PERFORMANCE,
                title="Physical GPU utilisation OK",
                detail=f"{gpu.name} at {gpu.gpu_util_pct:.1f}%.",
                recommendation="",
            ))

    # Temperature
    if gpu.temperature_c is not None:
        if gpu.temperature_c >= t["pgpu_temp_crit_c"]:
            findings.append(Finding(
                platform=pfx, resource=label,
                severity=Severity.CRITICAL,
                category=Category.PERFORMANCE,
                title="GPU temperature critical",
                detail=(
                    f"{gpu.name} on {hostname} is at {gpu.temperature_c:.0f}°C "
                    f"(critical: {t['pgpu_temp_crit_c']:.0f}°C). "
                    "Thermal throttling will degrade all users on this GPU."
                ),
                recommendation=(
                    "Check server cooling/airflow. Remove dust filters. "
                    "Verify GPU TDP is within server thermal envelope. "
                    "Consider reducing active vGPU instances temporarily."
                ),
            ))
        elif gpu.temperature_c >= t["pgpu_temp_warn_c"]:
            findings.append(Finding(
                platform=pfx, resource=label,
                severity=Severity.WARNING,
                category=Category.PERFORMANCE,
                title="GPU temperature elevated",
                detail=f"{gpu.name} at {gpu.temperature_c:.0f}°C.",
                recommendation="Check server cooling and airflow.",
            ))

    # Power draw vs limit
    if gpu.power_draw_w and gpu.power_limit_w and gpu.power_limit_w > 0:
        power_pct = (gpu.power_draw_w / gpu.power_limit_w) * 100
        if power_pct >= t["pgpu_power_warn_pct"]:
            findings.append(Finding(
                platform=pfx, resource=label,
                severity=Severity.WARNING,
                category=Category.PERFORMANCE,
                title="GPU near power limit",
                detail=(
                    f"{gpu.name} drawing {gpu.power_draw_w:.0f}W of "
                    f"{gpu.power_limit_w:.0f}W limit ({power_pct:.0f}%). "
                    "Power throttling may occur."
                ),
                recommendation=(
                    "Check server PSU headroom. GPU power capping may be active. "
                    "Reduce active workloads or increase the power limit if thermal budget allows."
                ),
            ))

    # VRAM
    vram_pct = gpu.vram_util_pct
    if vram_pct is not None and vram_pct >= t["pgpu_mem_warn_pct"]:
        findings.append(Finding(
            platform=pfx, resource=label,
            severity=Severity.WARNING,
            category=Category.CAPACITY,
            title="Physical GPU VRAM usage high",
            detail=(
                f"{gpu.name} VRAM at {vram_pct:.1f}% "
                f"({gpu.used_memory_mb}MB / {gpu.total_memory_mb}MB)."
            ),
            recommendation=(
                "High VRAM on the pGPU indicates vGPU slices are collectively "
                "consuming most frame-buffer. Consider a smaller profile size or "
                "fewer instances per GPU."
            ),
        ))

    # Idle GPU with no slices
    if (host_has_vgpu := len(gpu.vgpu_instances) == 0
            and gpu.gpu_util_pct is not None
            and gpu.gpu_util_pct < 5):
        findings.append(Finding(
            platform=pfx, resource=label,
            severity=Severity.INFO,
            category=Category.CAPACITY,
            title="Physical GPU idle with no active vGPU instances",
            detail=(
                f"{gpu.name} on {hostname} is powered on but has no vGPU instances "
                "and near-zero utilisation."
            ),
            recommendation=(
                "If this GPU is licensed for vGPU, verify the NVIDIA vGPU host driver "
                "is installed and vGPU instances are configured. "
                "If the server is outside peak hours, this may be expected."
            ),
        ))


# ── vGPU slice sizing ─────────────────────────────────────────────────────────

def _vgpu_slice_sizing(hostname, platform, gpu: PhysicalGPU, t, findings):
    pfx = platform.upper()
    underused, oversaturated = [], []

    for inst in gpu.vgpu_instances:
        fb_pct = inst.fb_util_pct
        sm = inst.sm_util_pct or 0
        enc = inst.encoder_util_pct or 0

        if inst.is_saturated:
            oversaturated.append(inst)
            sev = Severity.CRITICAL if fb_pct > 95 or sm > 95 else Severity.WARNING
            findings.append(Finding(
                platform=pfx,
                resource=f"{hostname} / {inst.profile.raw_name} ({inst.vm_name or inst.instance_id[:8]})",
                severity=sev,
                category=Category.PERFORMANCE,
                title="vGPU slice saturated — profile undersized",
                detail=(
                    f"Instance '{inst.vm_name or inst.instance_id[:12]}' "
                    f"({inst.profile.raw_name}): "
                    f"FB {fb_pct:.1f}%, SM {sm:.1f}%, Encoder {enc:.1f}%. "
                    "Users on this slice will see GPU stalls and frame drops."
                ),
                recommendation=(
                    f"Migrate this VM to a larger profile "
                    f"(e.g., {inst.profile.gpu_model}-{inst.profile.memory_mb * 2 // 1024}"
                    f"{inst.profile.profile_type}). "
                    "Drain the instance during off-peak and reassign."
                ),
            ))

        elif inst.is_idle:
            underused.append(inst)
            findings.append(Finding(
                platform=pfx,
                resource=f"{hostname} / {inst.profile.raw_name} ({inst.vm_name or inst.instance_id[:8]})",
                severity=Severity.INFO,
                category=Category.CAPACITY,
                title="vGPU slice underutilised — profile may be oversized",
                detail=(
                    f"Instance '{inst.vm_name or inst.instance_id[:12]}' "
                    f"({inst.profile.raw_name}): "
                    f"FB {fb_pct:.1f}%, SM {sm:.1f}%, Encoder {enc:.1f}%. "
                    f"This slice is consuming {inst.fb_total_mb}MB of frame buffer "
                    "with minimal activity."
                ),
                recommendation=(
                    f"Consider downsizing to a smaller profile "
                    f"(e.g., {inst.profile.gpu_model}-{max(1, inst.profile.memory_mb // 2 // 1024)}"
                    f"{inst.profile.profile_type}). "
                    "This frees up frame buffer for additional slices on the same GPU."
                ),
            ))

    if not underused and not oversaturated and gpu.vgpu_instances:
        findings.append(Finding(
            platform=pfx,
            resource=f"{hostname} / GPU {gpu.index} ({gpu.name})",
            severity=Severity.PASS,
            category=Category.PERFORMANCE,
            title="vGPU slice sizing appropriate",
            detail=(
                f"All {len(gpu.vgpu_instances)} slice(s) on {gpu.name} are "
                "within healthy utilisation bounds."
            ),
            recommendation="",
        ))

    # Encoder saturation check (remoting protocol bottleneck)
    for inst in gpu.vgpu_instances:
        enc = inst.encoder_util_pct or 0
        if enc >= t["encoder_saturated_pct"]:
            findings.append(Finding(
                platform=pfx,
                resource=f"{hostname} / {inst.profile.raw_name}",
                severity=Severity.WARNING,
                category=Category.PERFORMANCE,
                title="H.264/HEVC encoder saturated — remoting quality at risk",
                detail=(
                    f"Encoder utilisation at {enc:.1f}% "
                    f"(threshold: {t['encoder_saturated_pct']:.0f}%). "
                    "This directly throttles the display stream sent to end users — "
                    "they will see frame drops, lag, and visual artefacts."
                ),
                recommendation=(
                    "Reduce the number of sessions per slice, or switch from H.264 to "
                    "a more efficient codec (HEVC/AV1 if supported by the endpoint). "
                    "Check whether all users actually need remoted GPU or if some "
                    "could use software rendering."
                ),
            ))


# ── Licence profile ROI check ─────────────────────────────────────────────────

def _vgpu_profile_licence_check(hostname, platform, gpu: PhysicalGPU, t, findings):
    """Flag Q-profile (Quadro vDWS) instances that show no signs of needing it."""
    pfx = platform.upper()
    q_candidates = [
        inst for inst in gpu.vgpu_instances
        if inst.profile.profile_type == "Q"
        and inst.sm_util_pct is not None
        and inst.sm_util_pct < t["sm_q_profile_min_pct"]
        and inst.fb_util_pct < 40
    ]
    if q_candidates:
        names = [i.vm_name or i.instance_id[:10] for i in q_candidates]
        findings.append(Finding(
            platform=pfx,
            resource=f"{hostname} / GPU {gpu.index} ({gpu.name})",
            severity=Severity.WARNING,
            category=Category.CONFIGURATION,
            title="Quadro vDWS (Q) profiles used for low-intensity workloads",
            detail=(
                f"{len(q_candidates)} instance(s) on expensive Q-profile licences "
                f"with SM < {t['sm_q_profile_min_pct']:.0f}% and FB < 40%: "
                + ", ".join(names[:5])
                + ("…" if len(names) > 5 else "")
                + ". Q-profiles (Quadro vDWS) carry a significantly higher per-user "
                "NVIDIA licence cost than B-profiles (GRID vPC)."
            ),
            recommendation=(
                "Audit what applications these users actually run. "
                "If workloads are browser, Office, or light 2D, downgrade to a "
                f"{gpu.vgpu_instances[0].profile.gpu_model}-2B or "
                f"{gpu.vgpu_instances[0].profile.gpu_model}-4B profile. "
                "This can cut per-user GPU licence cost by 3–5× for qualifying users."
            ),
        ))


# ── Slice packing efficiency ──────────────────────────────────────────────────

def _slice_pack_efficiency(hostname, platform, gpu: PhysicalGPU, t, findings):
    """Is the physical GPU's frame buffer being well-utilised across all slices?"""
    pfx = platform.upper()
    eff = gpu.slice_efficiency_pct
    if eff is None:
        return

    if eff < t["slice_efficiency_warn_pct"]:
        allocated = gpu.allocated_fb_mb
        used = sum(i.fb_used_mb for i in gpu.vgpu_instances)
        findings.append(Finding(
            platform=pfx,
            resource=f"{hostname} / GPU {gpu.index} ({gpu.name})",
            severity=Severity.INFO,
            category=Category.CAPACITY,
            title="Low aggregate frame-buffer efficiency across slices",
            detail=(
                f"{gpu.name} on {hostname}: {used}MB of {allocated}MB allocated "
                f"frame buffer in use across {len(gpu.vgpu_instances)} slice(s) "
                f"({eff:.1f}% efficiency, threshold {t['slice_efficiency_warn_pct']:.0f}%). "
                "The GPU is delivering less density than it could."
            ),
            recommendation=(
                "Consider reducing vGPU profile sizes to pack more slices per GPU "
                "(e.g., 4× 4GB profiles instead of 2× 8GB). "
                "Alternatively, consolidate workloads and power off spare hosts "
                "during off-peak hours to reduce licence and power costs."
            ),
        ))
    else:
        findings.append(Finding(
            platform=pfx,
            resource=f"{hostname} / GPU {gpu.index} ({gpu.name})",
            severity=Severity.PASS,
            category=Category.CAPACITY,
            title="Frame-buffer slice packing efficient",
            detail=(
                f"{gpu.name}: {eff:.1f}% of allocated frame buffer in active use "
                f"across {len(gpu.vgpu_instances)} slices."
            ),
            recommendation="",
        ))


# ── Full passthrough ──────────────────────────────────────────────────────────

def _full_passthrough_check(hostname, platform, gpu: PhysicalGPU, findings):
    """A dedicated/passthrough GPU shared with no slicing is a density risk."""
    pfx = platform.upper()
    if gpu.total_memory_mb > 0:
        findings.append(Finding(
            platform=pfx,
            resource=f"{hostname} / GPU {gpu.index} ({gpu.name})",
            severity=Severity.INFO,
            category=Category.CAPACITY,
            title="GPU is full passthrough — no vGPU slicing",
            detail=(
                f"{hostname} has a {gpu.name} ({gpu.total_memory_mb}MB) "
                "passed through as a dedicated GPU (no vGPU partitioning). "
                "The entire GPU is consumed by one VM/session."
            ),
            recommendation=(
                "If multiple users share this host, consider enabling NVIDIA vGPU "
                "to slice the GPU across several sessions — each getting their own "
                "frame buffer and dedicated encoder/decoder. "
                "For single-user workstations (CAD/VR) full passthrough is correct."
            ),
        ))


# ── GPU process hogs ──────────────────────────────────────────────────────────

def _gpu_process_hogs(hostname, platform, host: HostGPUData, t, findings):
    pfx = platform.upper()
    for proc in host.top_gpu_processes:
        if proc.utilization_pct >= t["process_gpu_hog_pct"]:
            findings.append(Finding(
                platform=pfx,
                resource=f"{hostname} / PID {proc.pid}",
                severity=Severity.WARNING,
                category=Category.PERFORMANCE,
                title=f"Single process consuming >60% GPU: {proc.process_name or 'unknown'}",
                detail=(
                    f"Process '{proc.process_name or 'unknown'}' (PID {proc.pid}) "
                    f"is using {proc.utilization_pct:.1f}% of GPU on {hostname}. "
                    "This can starve other users' vGPU slices of compute time."
                ),
                recommendation=(
                    "Identify the process and user account. "
                    "Apply NVIDIA vGPU scheduling policy (best-effort vs equal-share) "
                    "or set GPU resource limits via the hypervisor. "
                    "Consider moving heavy-compute users to dedicated C-profile slices."
                ),
            ))
