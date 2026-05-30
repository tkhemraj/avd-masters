"""GPU and vGPU data models — shared across AVD, RDS, and Citrix collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import re


# ── vGPU profile parsing ──────────────────────────────────────────────────────
#
# NVIDIA vGPU profile naming: GRID {GPU}-{memory_gb}{type}
#   e.g. GRID A16-4Q, GRID T4-2B, GRID A10-10C, GRID RTX6000-8Q
#
# Profile types:
#   B = Virtual PC       — basic 2D/Office, lowest cost (GRID vPC licence)
#   Q = Quadro vDWS      — professional CAD/3D (expensive vDWS licence)
#   C = Compute/CUDA     — AI/ML/render (vCS licence)
#   A = App Streaming    — single-app, no persistent desktop

_PROFILE_RE = re.compile(
    r"(?:GRID\s+)?([A-Za-z0-9]+)-(\d+)([BQCA])\b",
    re.IGNORECASE,
)

_PROFILE_LABELS = {
    "B": "Virtual PC",
    "Q": "Quadro vDWS",
    "C": "vCompute",
    "A": "App Streaming",
}

# Azure NV-series GPU partition fractions by VM size suffix
_AZURE_GPU_FRACTIONS: dict[str, str] = {
    "NV4as":  "1/8 A10",
    "NV8as":  "1/4 A10",
    "NV16as": "1/2 A10",
    "NV32as": "1× A10",
    "NV6ads": "1/6 A10",
    "NV12ads":"1/6 A10",
    "NV18ads":"1/2 A10",
    "NV36ads":"1× A10",
    "NV6":    "1/2 M60",
    "NV12":   "1× M60",
    "NV24":   "2× M60",
}


@dataclass
class VGPUProfile:
    raw_name: str
    gpu_model: str       # "T4", "A16", "A10", "RTX6000"
    memory_mb: int       # frame-buffer allocation in MB
    profile_type: str    # "B", "Q", "C", "A", "MIG", "Passthrough", "Partition"
    max_instances: Optional[int] = None

    @property
    def type_label(self) -> str:
        return _PROFILE_LABELS.get(self.profile_type, self.profile_type)

    @property
    def is_expensive_licence(self) -> bool:
        """Q (Quadro vDWS) and C (vCS) profiles carry higher per-user licence cost."""
        return self.profile_type in ("Q", "C")

    @classmethod
    def parse(cls, name: str) -> "VGPUProfile":
        m = _PROFILE_RE.search(name)
        if m:
            gpu_model = m.group(1)
            memory_mb = int(m.group(2)) * 1024
            profile_type = m.group(3).upper()
            return cls(
                raw_name=name,
                gpu_model=gpu_model,
                memory_mb=memory_mb,
                profile_type=profile_type,
            )
        # Fallback: MIG, full passthrough, Azure partition
        if "mig" in name.lower():
            return cls(raw_name=name, gpu_model=name, memory_mb=0, profile_type="MIG")
        return cls(raw_name=name, gpu_model=name, memory_mb=0, profile_type="Passthrough")


@dataclass
class GPUEngine:
    """Utilisation of one GPU engine block."""
    engine_type: str       # "3D", "Compute", "Copy", "VideoEncode", "VideoDecode", "Overlay"
    utilization_pct: float
    adapter: Optional[str] = None
    pid: Optional[int] = None
    process_name: Optional[str] = None


@dataclass
class VGPUInstance:
    """One live vGPU slice assigned to a VM or session."""
    instance_id: str
    profile: VGPUProfile
    gpu_index: int
    vm_name: Optional[str] = None
    session_user: Optional[str] = None
    fb_used_mb: int = 0
    fb_total_mb: int = 0
    sm_util_pct: Optional[float] = None       # shader/compute utilisation
    mem_util_pct: Optional[float] = None      # memory-bandwidth utilisation
    encoder_util_pct: Optional[float] = None
    decoder_util_pct: Optional[float] = None
    active_channels: Optional[int] = None

    @property
    def fb_util_pct(self) -> float:
        if self.fb_total_mb == 0:
            return 0.0
        return round((self.fb_used_mb / self.fb_total_mb) * 100, 1)

    @property
    def is_idle(self) -> bool:
        """No meaningful GPU activity — profile may be oversized."""
        sm = self.sm_util_pct or 0
        fb = self.fb_util_pct
        return sm < 5 and fb < 20

    @property
    def is_saturated(self) -> bool:
        sm = self.sm_util_pct or 0
        fb = self.fb_util_pct
        enc = self.encoder_util_pct or 0
        return sm > 85 or fb > 90 or enc > 85


@dataclass
class PhysicalGPU:
    """One physical GPU on a host."""
    index: int
    name: str
    total_memory_mb: int
    used_memory_mb: Optional[int] = None
    gpu_util_pct: Optional[float] = None
    mem_util_pct: Optional[float] = None
    encoder_util_pct: Optional[float] = None
    decoder_util_pct: Optional[float] = None
    temperature_c: Optional[float] = None
    power_draw_w: Optional[float] = None
    power_limit_w: Optional[float] = None
    driver_version: Optional[str] = None
    vgpu_instances: list[VGPUInstance] = field(default_factory=list)
    engines: list[GPUEngine] = field(default_factory=list)

    @property
    def vram_util_pct(self) -> Optional[float]:
        if self.used_memory_mb is None or self.total_memory_mb == 0:
            return None
        return round((self.used_memory_mb / self.total_memory_mb) * 100, 1)

    @property
    def active_slice_count(self) -> int:
        return len(self.vgpu_instances)

    @property
    def allocated_fb_mb(self) -> int:
        """Total frame buffer allocated across all vGPU instances."""
        return sum(v.fb_total_mb for v in self.vgpu_instances)

    @property
    def slice_efficiency_pct(self) -> Optional[float]:
        """Proportion of allocated FB that is actually in use."""
        allocated = self.allocated_fb_mb
        if allocated == 0:
            return None
        used = sum(v.fb_used_mb for v in self.vgpu_instances)
        return round((used / allocated) * 100, 1)


@dataclass
class HostGPUData:
    """GPU state for a single monitored host."""
    hostname: str
    platform: str          # "avd" | "rds" | "citrix"
    physical_gpus: list[PhysicalGPU] = field(default_factory=list)
    top_gpu_processes: list[GPUEngine] = field(default_factory=list)
    has_nvidia: bool = False
    has_vgpu: bool = False
    azure_vm_size: Optional[str] = None    # for Azure partition identification
    errors: list[str] = field(default_factory=list)
    collected_at: datetime = field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc))

    @property
    def vgpu_instance_count(self) -> int:
        return sum(g.active_slice_count for g in self.physical_gpus)

    @property
    def total_vram_mb(self) -> int:
        return sum(g.total_memory_mb for g in self.physical_gpus)


@dataclass
class GPUSnapshot:
    """GPU data from all monitored hosts across all platforms."""
    collected_at: datetime
    hosts: dict[str, HostGPUData] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def total_vgpu_instances(self) -> int:
        return sum(h.vgpu_instance_count for h in self.hosts.values())

    @property
    def hosts_with_gpu(self) -> list[HostGPUData]:
        return [h for h in self.hosts.values() if h.physical_gpus]
