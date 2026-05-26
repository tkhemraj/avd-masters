"""
AVD Masters — Dynamic SKU Discovery

Fetches current Azure VM SKUs (especially GPU ones) dynamically from Azure,
scoped to the regions the customer actually has resources in.

This replaces the old static catalog approach with fresh, region-aware data.
Live data is enriched with high-fidelity model + VRAM knowledge so that
cost calculations, tagging, and recommendations are accurate.
"""

from __future__ import annotations

import logging
from typing import Optional

from azure.mgmt.compute import ComputeManagementClient

from avd_masters.catalog import GpuSpec, NVIDIA, AMD

logger = logging.getLogger(__name__)


def fetch_gpu_skus_for_regions(
    compute_client: ComputeManagementClient,
    regions: list[str],
) -> dict[str, GpuSpec]:
    """
    Dynamically discover GPU-capable VM SKUs in the given regions.

    Returns a dict of lowercase SKU name -> high-quality GpuSpec.
    Uses a combination of live Azure capability data + curated high-fidelity
    GPU model profiles for accurate VRAM, generation, and vendor info.
    """
    discovered: dict[str, GpuSpec] = {}

    for region in regions:
        try:
            skus = compute_client.resource_skus.list(
                filter=f"location eq '{region}' and resourceType eq 'virtualMachines'"
            )

            for sku in skus:
                if not sku.capabilities:
                    continue

                # Extract all interesting capabilities
                caps = {c.name: c.value for c in sku.capabilities if c.name and c.value}

                gpu_count = _parse_float(caps.get("GPUs") or caps.get("AcceleratorCount"))
                gpu_model_raw = caps.get("GPUModel") or caps.get("AcceleratorModel")
                gpu_manufacturer = (caps.get("GPUManufacturer") or caps.get("AcceleratorManufacturer") or "").lower()

                if not gpu_count or gpu_count <= 0 or not gpu_model_raw:
                    continue

                # Normalize model name (Azure returns things like "NVIDIA H100 80GB", "AMD MI300X" etc.)
                model = _normalize_gpu_model(gpu_model_raw)

                vendor = AMD if "amd" in gpu_manufacturer or "mi" in model.lower() else NVIDIA

                # High-fidelity VRAM lookup (preferred over crude multiplication)
                vram_mb = _resolve_vram_mb(model, gpu_count, caps)

                spec = GpuSpec(
                    vendor=vendor,
                    model=model,
                    gpu_count=gpu_count,
                    vram_mb=vram_mb,
                    generation=_guess_generation(model),
                    notes=_build_notes(model, caps),
                )

                discovered[sku.name.lower()] = spec

        except Exception as exc:
            logger.warning("Failed to fetch SKUs for region %s: %s", region, exc)

    logger.info("Dynamically discovered %d GPU SKUs across %d regions", len(discovered), len(regions))
    return discovered


# =============================================================================
# High-fidelity GPU profile data (accurate as of 2026)
# =============================================================================

# Base VRAM in MB for full physical GPUs (used when Azure doesn't expose exact memory)
_KNOWN_GPU_VRAM_MB: dict[str, int] = {
    # NVIDIA Hopper family (2023-2026)
    "h100": 81920,          # 80 GB standard (most common)
    "h100 94gb": 96256,
    "h100 96gb": 98304,
    "h200": 144384,         # ~141 GiB HBM3e
    # Ampere
    "a100": 81920,
    "a100 40gb": 40960,
    # Ada Lovelace
    "l40s": 49152,          # 48 GB
    "l40": 49152,
    "a10": 24576,           # 24 GB
    "rtx 6000": 49152,
    # Blackwell (emerging)
    "b200": 188416,
    "gb200": 192000,
    # AMD CDNA3 / RDNA
    "mi300x": 1572864,      # 192 GB HBM3 (CDNA3)
    "v620": 32768,
    "v710": 24576,
    "radeon pro v620": 32768,
    "radeon pro v710": 24576,
}

# Common aliases Azure might use
_MODEL_ALIASES = {
    "nvidia h100": "H100",
    "nvidia h200": "H200",
    "nvidia a100": "A100",
    "nvidia l40s": "L40S",
    "nvidia a10": "A10",
    "amd mi300x": "MI300X",
    "amd radeon pro v620": "Radeon PRO V620",
}


def _normalize_gpu_model(raw: str) -> str:
    raw = raw.strip()
    lower = raw.lower()

    for alias, canonical in _MODEL_ALIASES.items():
        if alias in lower:
            return canonical

    # Strip common prefixes
    for prefix in ("nvidia ", "amd ", "tesla ", "accelerator "):
        if lower.startswith(prefix):
            raw = raw[len(prefix):].strip()
            lower = raw.lower()

    # Title case nicely
    return raw.upper() if raw.islower() else raw


def _resolve_vram_mb(model: str, gpu_count: float, caps: dict[str, str]) -> int:
    """Best-effort accurate VRAM. Prefer explicit fields, then known profiles."""
    model_lower = model.lower()

    # 1. Look for explicit memory capability from Azure if present
    for key in ("AcceleratorMemoryInMB", "GPUMemoryMB", "AcceleratorMemoryMB", "MemoryMB"):
        if key in caps:
            try:
                mem = int(float(caps[key]))
                if mem > 1024:  # ignore nonsense small values
                    return int(mem * gpu_count)
            except (ValueError, TypeError):
                pass

    # 2. High-fidelity static profile lookup
    for key, vram in _KNOWN_GPU_VRAM_MB.items():
        if key in model_lower:
            return int(vram * gpu_count)

    # 3. Fallback heuristics (better than before but still estimate)
    if "h100" in model_lower or "h200" in model_lower:
        base = 96256 if "94" in model_lower or "96" in model_lower else 81920
        return int(base * gpu_count)
    if "a100" in model_lower:
        return int(81920 * gpu_count)
    if "l40" in model_lower:
        return int(49152 * gpu_count)
    if "a10" in model_lower:
        return int(24576 * gpu_count)
    if "mi300" in model_lower:
        return int(1572864 * gpu_count)

    # Last resort generic
    return int(gpu_count * 16384)


def _build_notes(model: str, caps: dict[str, str]) -> str:
    """Attach useful context discovered at runtime."""
    notes = []
    if "vCPUs" in caps:
        notes.append(f"{caps['vCPUs']} vCPU")
    if "MemoryGB" in caps:
        notes.append(f"{caps['MemoryGB']} GB RAM")

    # Flag interesting variants
    m = model.lower()
    if "h100" in m and ("94" in m or "96" in m):
        notes.append("High-memory variant")
    if caps.get("GPUs") and float(caps.get("GPUs", 0)) >= 4:
        notes.append("Dense node")

    return " • ".join(notes) if notes else ""


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _guess_generation(model: str) -> str:
    model = model.upper()
    if "H100" in model or "H200" in model:
        return "Hopper"
    if "A100" in model:
        return "Ampere"
    if "L40" in model or "A10" in model:
        return "Ada"
    if "MI300" in model:
        return "CDNA3"
    return ""


