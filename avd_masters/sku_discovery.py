"""
AVD Masters — Dynamic SKU Discovery

Fetches current Azure VM SKUs (especially GPU ones) dynamically from Azure,
scoped to the regions the customer actually has resources in.

This replaces the old static catalog approach with fresh, region-aware data.
"""

from __future__ import annotations

import logging
from typing import Optional

from azure.mgmt.compute import ComputeManagementClient

from avd_masters.catalog import GpuSpec, NVIDIA, AMD, CATALOG  # we'll evolve this

logger = logging.getLogger(__name__)


def fetch_gpu_skus_for_regions(
    compute_client: ComputeManagementClient,
    regions: list[str],
) -> dict[str, GpuSpec]:
    """
    Dynamically discover GPU-capable VM SKUs in the given regions.

    Returns a dict of lowercase SKU name -> GpuSpec.
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

                # Look for GPU capabilities
                gpu_count = None
                gpu_manufacturer = None
                gpu_model = None
                vram = None

                for cap in sku.capabilities:
                    if cap.name == "GPUs":
                        try:
                            gpu_count = float(cap.value)
                        except (ValueError, TypeError):
                            continue
                    if cap.name == "GPUModel":
                        gpu_model = cap.value
                    if cap.name == "GPUManufacturer":
                        gpu_manufacturer = cap.value.lower() if cap.value else None

                if gpu_count and gpu_count > 0 and gpu_model:
                    vendor = AMD if gpu_manufacturer and "amd" in gpu_manufacturer else NVIDIA

                    # Very rough VRAM estimate — in real version we'd enrich this
                    vram_mb = int(gpu_count * 24576) if "H100" in gpu_model or "A100" in gpu_model else int(gpu_count * 16384)

                    spec = GpuSpec(
                        vendor=vendor,
                        model=gpu_model,
                        gpu_count=gpu_count,
                        vram_mb=vram_mb,
                        generation=_guess_generation(gpu_model),
                    )

                    discovered[sku.name.lower()] = spec

        except Exception as exc:
            logger.warning("Failed to fetch SKUs for region %s: %s", region, exc)

    logger.info("Dynamically discovered %d GPU SKUs across %d regions", len(discovered), len(regions))
    return discovered


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


def refresh_catalog(
    compute_client: Optional[ComputeManagementClient] = None,
    regions: Optional[list[str]] = None,
) -> None:
    """
    Refreshes the in-memory catalog with live data from Azure.

    If compute_client and regions are provided, it will do a live fetch.
    Otherwise it falls back to the static catalog.
    """
    global CATALOG

    if compute_client and regions:
        live_skus = fetch_gpu_skus_for_regions(compute_client, regions)
        if live_skus:
            CATALOG.update({k: v for k, v in live_skus.items()})
            logger.info("Catalog refreshed with live Azure SKU data")
    else:
        logger.info("Using static catalog (no Azure client provided for dynamic lookup)")
