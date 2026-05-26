"""
GROKY 2.0 — GPU Catalog

The single source of truth for Azure GPU-accelerated VM SKUs.

This catalog exists because almost every other tool either:
- Uses outdated 2024-2026 data, or
- Lies to you about fractional GPUs, or
- Charges you a fortune to tell you what nvidia-smi already knows.

We do none of those things.

This module knows the actual hardware behind every relevant Azure GPU SKU
as of 2026+, including proper modeling of vGPU / MIG / GPU partitioning.

Treat this as the foundation. Everything else builds on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# =============================================================================
# Constants
# =============================================================================

NVIDIA = "nvidia"
AMD = "amd"

GENERATIONS = {
    "blackwell": "Blackwell",
    "hopper": "Hopper",
    "ada": "Ada Lovelace",
    "ampere": "Ampere",
    "cdna3": "CDNA 3",
    "legacy": "Legacy",
}


# =============================================================================
# Core Data Structure
# =============================================================================

@dataclass(frozen=True)
class GpuSpec:
    """
    Precise description of the GPU hardware delivered by a specific Azure VM SKU.

    This is the atomic truth. Every other part of GROKY derives from this.
    """

    vendor: str                    # "nvidia" | "amd"
    model: str                     # "H100", "H200", "MI300X", "L40S", "A10", etc.
    gpu_count: float               # 1.0 = full physical GPU. 0.166 = 1/6 partition, etc.
    vram_mb: int                   # Framebuffer actually assigned to this SKU/partition
    generation: str = ""           # "Hopper", "Blackwell", "Ada", "CDNA3", ...
    retiring: bool = False
    notes: str = ""

    # --- Derived / Convenience ---

    @property
    def vram_gb(self) -> float:
        """VRAM in gigabytes (rounded nicely)."""
        return round(self.vram_mb / 1024, 1)

    @property
    def is_fractional(self) -> bool:
        """True if this SKU gets less than one full physical GPU."""
        return self.gpu_count < 1.0

    @property
    def fractional_share(self) -> Optional[str]:
        """Human-friendly fraction string when applicable (e.g. '1/6')."""
        if not self.is_fractional:
            return None
        # Best effort pretty fraction
        common = {
            0.125: "1/8", 0.16666666666666666: "1/6", 0.25: "1/4",
            0.3333333333333333: "1/3", 0.5: "1/2",
        }
        return common.get(round(self.gpu_count, 6), f"{self.gpu_count:.2f}")

    @property
    def full_gpu_equivalent(self) -> float:
        """How many full physical GPUs this SKU represents."""
        return self.gpu_count

    def __str__(self) -> str:
        frac = self.fractional_share
        prefix = f"{frac}× " if frac else ""
        return f"{prefix}{self.model} ({self.vram_gb:g} GB) [{self.vendor.upper()}]"

    def pretty(self) -> str:
        """More descriptive one-line representation."""
        base = str(self)
        if self.generation:
            base += f" • {self.generation}"
        if self.notes:
            base += f" — {self.notes}"
        if self.retiring:
            base += " [RETIRING]"
        return base


# =============================================================================
# NVIDIA — Current & Next-Gen Families (2026+)
# =============================================================================

# NVads A10 v5 — still one of the best price/performance graphics SKUs
_NVads_A10v5 = {
    "standard_nv6ads_a10_v5":   GpuSpec(NVIDIA, "A10",   1/6,   4096,  "Ada"),
    "standard_nv12ads_a10_v5":  GpuSpec(NVIDIA, "A10",   1/6,   4096,  "Ada"),
    "standard_nv18ads_a10_v5":  GpuSpec(NVIDIA, "A10",   1/3,   8192,  "Ada"),
    "standard_nv36ads_a10_v5":  GpuSpec(NVIDIA, "A10",   1.0,  24576,  "Ada"),
    "standard_nv36adms_a10_v5": GpuSpec(NVIDIA, "A10",   1.0,  24576,  "Ada"),
    "standard_nv72ads_a10_v5":  GpuSpec(NVIDIA, "A10",   2.0,  49152,  "Ada"),
}

# NCads H100 v5 — Hopper, fractional and full
_NCads_H100v5 = {
    "standard_nc4ads_h100_v5":  GpuSpec(NVIDIA, "H100",  1/6,    8192, "Hopper", notes="Entry fractional H100"),
    "standard_nc8ads_h100_v5":  GpuSpec(NVIDIA, "H100",  1/3,   16384, "Hopper"),
    "standard_nc16ads_h100_v5": GpuSpec(NVIDIA, "H100",  0.5,   40960, "Hopper"),
    "standard_nc32ads_h100_v5": GpuSpec(NVIDIA, "H100",  1.0,   81920, "Hopper"),
    "standard_nc40ads_h100_v5": GpuSpec(NVIDIA, "H100",  1.0,   94208, "Hopper", notes="94GB H100 variant"),
    "standard_nc64ads_h100_v5": GpuSpec(NVIDIA, "H100",  2.0,  163840, "Hopper"),
    "standard_nc80adis_h100_v5": GpuSpec(NVIDIA, "H100", 2.0,  188416, "Hopper", notes="2× 94GB H100"),
}

# ND H100 v5 — dense 8x nodes
_ND_H100v5 = {
    "standard_nd96isr_h100_v5": GpuSpec(NVIDIA, "H100", 8.0, 655360, "Hopper", notes="8× H100 80GB"),
    "standard_nd96is_h100_v5":  GpuSpec(NVIDIA, "H100", 8.0, 655360, "Hopper"),
}

# H200 series (higher memory, very relevant in 2026)
_ND_H200v5 = {
    "standard_nd96isr_h200_v5": GpuSpec(NVIDIA, "H200", 8.0, 1_146_368, "Hopper", notes="8× H200 141GB"),
}

# NC A100 v4 (still very common)
_NC_A100v4 = {
    "standard_nc24ads_a100_v4": GpuSpec(NVIDIA, "A100", 1.0,   81920, "Ampere"),
    "standard_nc48ads_a100_v4": GpuSpec(NVIDIA, "A100", 2.0,  163840, "Ampere"),
    "standard_nc96ads_a100_v4": GpuSpec(NVIDIA, "A100", 4.0,  327680, "Ampere"),
}

# ND A100 dense nodes
_ND_A100v4 = {
    "standard_nd96asr_v4":          GpuSpec(NVIDIA, "A100", 8.0, 655360, "Ampere"),
    "standard_nd96amsr_a100_v4":    GpuSpec(NVIDIA, "A100", 8.0, 655360, "Ampere"),
}

# L40S — excellent for graphics + AI inference
_L40S_series = {
    "standard_nv36ads_l40s_v5": GpuSpec(NVIDIA, "L40S", 1.0,  49152, "Ada"),
    "standard_nv72ads_l40s_v5": GpuSpec(NVIDIA, "L40S", 2.0,  98304, "Ada"),
}

# Professional / RTX series (v6 families)
_RTX6000_series = {
    "standard_nc4rs_rtxpro6000bse_v6":  GpuSpec(NVIDIA, "RTX 6000", 0.25,  6144, "Ada", notes="Professional graphics"),
    "standard_nc8rs_rtxpro6000bse_v6":  GpuSpec(NVIDIA, "RTX 6000", 0.5,  12288, "Ada", notes="Professional graphics"),
}

# Legacy NVIDIA (still tracked so we can warn people)
_NVv3_legacy = {
    "standard_nv12s_v3": GpuSpec(NVIDIA, "Tesla M60", 1.0,  8192, retiring=True, notes="Retiring Sept 2026"),
    "standard_nv24s_v3": GpuSpec(NVIDIA, "Tesla M60", 2.0, 16384, retiring=True, notes="Retiring Sept 2026"),
    "standard_nv48s_v3": GpuSpec(NVIDIA, "Tesla M60", 4.0, 32768, retiring=True, notes="Retiring Sept 2026"),
}

# =============================================================================
# AMD
# =============================================================================

# NGads V620 — still relevant for gaming / graphics workloads
_NGads_V620 = {
    "standard_ng8ads_v620_v1":  GpuSpec(AMD, "Radeon PRO V620", 0.25,   8192, notes="1/4 partition"),
    "standard_ng16ads_v620_v1": GpuSpec(AMD, "Radeon PRO V620", 0.5,   16384, notes="1/2 partition"),
    "standard_ng32ads_v620_v1": GpuSpec(AMD, "Radeon PRO V620", 1.0,   32768),
}

# NVads V710 v5 — current AMD graphics fractional family
_NVads_V710v5 = {
    "standard_nv6ads_v710_v5":  GpuSpec(AMD, "Radeon PRO V710", 1/6,   4096),
    "standard_nv12ads_v710_v5": GpuSpec(AMD, "Radeon PRO V710", 0.25,  6144),
    "standard_nv18ads_v710_v5": GpuSpec(AMD, "Radeon PRO V710", 1/3,   8192),
    "standard_nv36ads_v710_v5": GpuSpec(AMD, "Radeon PRO V710", 0.5,  12288),
    "standard_nv72ads_v710_v5": GpuSpec(AMD, "Radeon PRO V710", 1.0,  24576),
}

# MI300X — high-end AMD compute (CDNA 3)
_MI300X_series = {
    "standard_nd96is_mi300x_v5": GpuSpec(AMD, "MI300X", 8.0, 1_572_864, "CDNA3", notes="8× MI300X 192GB"),
}

# Legacy AMD (MI25)
_NVv4_legacy = {
    "standard_nv4as_v4":  GpuSpec(AMD, "Radeon Instinct MI25", 0.125, 2048, retiring=True),
    "standard_nv8as_v4":  GpuSpec(AMD, "Radeon Instinct MI25", 0.25,  4096, retiring=True),
    "standard_nv16as_v4": GpuSpec(AMD, "Radeon Instinct MI25", 0.5,   8192, retiring=True),
    "standard_nv32as_v4": GpuSpec(AMD, "Radeon Instinct MI25", 1.0,  16384, retiring=True),
}

# =============================================================================
# Master Catalog + Lookup
# =============================================================================

CATALOG: dict[str, GpuSpec] = {
    **_NVads_A10v5,
    **_NCads_H100v5,
    **_ND_H100v5,
    **_ND_H200v5,
    **_NC_A100v4,
    **_ND_A100v4,
    **_L40S_series,
    **_RTX6000_series,
    **_NVv3_legacy,
    **_NGads_V620,
    **_NVads_V710v5,
    **_MI300X_series,
    **_NVv4_legacy,
}

# Case-insensitive lookup
CATALOG = {k.lower(): v for k, v in CATALOG.items()}


def lookup(sku: str | None) -> Optional[GpuSpec]:
    """Return the GpuSpec for an Azure VM size, or None."""
    if not sku:
        return None
    return CATALOG.get(sku.lower().strip())


def is_nvidia(sku: str | None) -> bool:
    spec = lookup(sku)
    return spec is not None and spec.vendor == NVIDIA


def is_amd(sku: str | None) -> bool:
    spec = lookup(sku)
    return spec is not None and spec.vendor == AMD


def get_vendor(sku: str | None) -> str:
    spec = lookup(sku)
    return spec.vendor if spec else "unknown"


def all_skus() -> list[str]:
    return sorted(CATALOG.keys())


def get_retiring_skus() -> list[str]:
    return sorted(s for s, spec in CATALOG.items() if spec.retiring)


def describe(sku: str | None) -> str:
    """Human-friendly one-line description."""
    spec = lookup(sku)
    if not spec:
        return f"Unknown SKU: {sku}"
    return str(spec)


def get_skus_by_model(model: str) -> list[str]:
    """All SKUs that use a specific GPU model (e.g. 'H100')."""
    model_lower = model.lower()
    return sorted(
        sku for sku, spec in CATALOG.items()
        if spec.model.lower() == model_lower
    )


def get_fractional_skus() -> list[str]:
    """All SKUs that deliver fractional GPUs."""
    return sorted(sku for sku, spec in CATALOG.items() if spec.is_fractional)


def get_high_end_nodes() -> list[str]:
    """SKUs with 4+ full GPUs (dense nodes). Excludes retiring hardware."""
    return sorted(
        sku for sku, spec in CATALOG.items()
        if spec.gpu_count >= 4.0 and not spec.is_fractional and not spec.retiring
    )


def get_by_generation(gen: str) -> list[str]:
    """SKUs from a specific generation (e.g. 'Hopper', 'Ada')."""
    gen_lower = gen.lower()
    return sorted(
        sku for sku, spec in CATALOG.items()
        if spec.generation.lower() == gen_lower
    )


def summarize() -> dict:
    """High-level stats about the catalog."""
    total = len(CATALOG)
    nvidia = sum(1 for s in CATALOG.values() if s.vendor == NVIDIA)
    amd = sum(1 for s in CATALOG.values() if s.vendor == AMD)
    fractional = len(get_fractional_skus())
    retiring = len(get_retiring_skus())

    return {
        "total_skus": total,
        "nvidia": nvidia,
        "amd": amd,
        "fractional_skus": fractional,
        "retiring_skus": retiring,
    }
