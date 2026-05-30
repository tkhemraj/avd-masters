"""
AVD Masters — FinOps / Cost Attribution Module

This module enables real cost calculation and auto-tagging capabilities.

Core idea:
- Calculate accurate **cost per GPU-second** for any SKU we monitor.
- Support different pricing models (PayGo, Reserved, Spot).
- Provide data that can be used for Azure tagging, showback, and chargeback.

This is one of the highest-value features for large Microsoft customers.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import requests

from avd_masters.catalog import GpuSpec, lookup
from avd_masters import sku_discovery

logger = logging.getLogger(__name__)

# =============================================================================
# Pricing Models
# =============================================================================

@dataclass
class PricingModel:
    name: str                    # "paygo", "reserved", "spot"
    discount: float = 1.0        # 1.0 = full price, 0.7 = 30% off, etc.


PAYGO = PricingModel("paygo", 1.0)
RESERVED = PricingModel("reserved", 0.60)   # Rough average for 1-year RI
SPOT = PricingModel("spot", 0.40)           # Very rough average

DEFAULT_PRICING = PAYGO


# =============================================================================
# Azure Retail Prices API Client (lightweight)
# =============================================================================

AZURE_PRICES_API = "https://prices.azure.com/api/retail/prices"

# Simple in-memory cache
_price_cache: dict[str, float] = {}
_cache_ttl = timedelta(hours=6)
_cache_time: Optional[datetime] = None
_cache_lock = threading.Lock()

# Azure region names are lowercase alphanumeric with no spaces
_REGION_RE = re.compile(r"^[a-z][a-z0-9]{1,29}$")
# Azure VM SKU names: letters, digits, underscores only
_SKU_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def _validate_region(region: str) -> str:
    """Raise ValueError if region contains characters that could inject OData syntax."""
    if not _REGION_RE.match(region):
        raise ValueError(f"Invalid Azure region name: {region!r}")
    return region


def _validate_sku(sku: str) -> str:
    """Raise ValueError if SKU contains characters that could inject OData syntax."""
    if not _SKU_RE.match(sku):
        raise ValueError(f"Invalid Azure SKU name: {sku!r}")
    return sku


def get_gpu_hourly_price(sku: str, region: str = "eastus") -> Optional[float]:
    """
    Fetch approximate hourly price for a GPU VM SKU from Azure Retail Prices API.

    This is best-effort. Real enterprises often have negotiated rates.
    """
    try:
        region = _validate_region(region)
        sku_validated = _validate_sku(sku)
    except ValueError as exc:
        logger.warning("Invalid parameter for price lookup: %s", exc)
        return None

    cache_key = f"{sku_validated.lower()}:{region}"

    with _cache_lock:
        if _cache_time and datetime.utcnow() - _cache_time < _cache_ttl:
            if cache_key in _price_cache:
                return _price_cache[cache_key]

    try:
        sku_suffix = sku_validated.split("_")[-1]
        params = {
            "api-version": "2023-01-01-preview",
            "$filter": (
                f"serviceName eq 'Virtual Machines' "
                f"and armRegionName eq '{region}' "
                f"and contains(skuName, '{sku_suffix}')"
            ),
        }

        resp = requests.get(AZURE_PRICES_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("Items", []):
            if "GPU" in item.get("productName", "") or "H100" in item.get("skuName", "") or "A10" in item.get("skuName", ""):
                price = float(item.get("retailPrice", 0))
                if price > 0:
                    with _cache_lock:
                        _price_cache[cache_key] = price
                        # module-level _cache_time update — safe under lock
                        globals()["_cache_time"] = datetime.utcnow()
                    return price

        if data.get("Items"):
            price = float(data["Items"][0].get("retailPrice", 0))
            if price > 0:
                with _cache_lock:
                    _price_cache[cache_key] = price
                    globals()["_cache_time"] = datetime.utcnow()
                return price

    except Exception as exc:
        logger.warning("Failed to fetch Azure price for %s/%s: %s", sku, region, type(exc).__name__)

    return None


# =============================================================================
# Cost Calculation
# =============================================================================

def calculate_gpu_hourly_cost(
    spec: GpuSpec,
    sku: str,
    region: str = "eastus",
    pricing: PricingModel = DEFAULT_PRICING,
) -> Optional[float]:
    """
    Estimate the hourly cost attributable to the GPUs on this SKU.

    This is an approximation. Real cost depends on many factors
    (software licensing, storage, networking, reserved pricing, etc.).
    """
    # First try to get real price from Azure
    full_vm_price = get_gpu_hourly_price(sku, region)

    if full_vm_price is None:
        # Very rough fallback estimates (USD) for common GPU VMs
        fallback_prices = {
            "h100": 4.50,
            "a100": 3.20,
            "a10": 1.80,
            "v620": 1.10,
            "l40s": 2.10,
            "mi300x": 5.80,
        }
        model_lower = spec.model.lower()
        full_vm_price = next(
            (price for key, price in fallback_prices.items() if key in model_lower),
            2.50,  # generic fallback
        )

    # Adjust for fractional GPUs and pricing model
    gpu_cost = full_vm_price * spec.gpu_count * pricing.discount
    return round(gpu_cost, 4)


def calculate_cost_per_second(
    spec: GpuSpec,
    sku: str,
    region: str = "eastus",
    pricing: PricingModel = DEFAULT_PRICING,
) -> Optional[float]:
    """Cost per GPU-second for this spec."""
    hourly = calculate_gpu_hourly_cost(spec, sku, region, pricing)
    if hourly is None:
        return None
    return hourly / 3600


def estimate_cost_for_samples(
    gpu_seconds: float,
    spec: GpuSpec,
    sku: str,
    region: str = "eastus",
    pricing: PricingModel = DEFAULT_PRICING,
) -> Optional[float]:
    """
    Given total GPU-seconds consumed, return estimated dollar cost.
    """
    per_second = calculate_cost_per_second(spec, sku, region, pricing)
    if per_second is None:
        return None
    return round(gpu_seconds * per_second, 4)


# =============================================================================
# Azure Tag Generation (for auto-tagging)
# =============================================================================

def generate_cost_tags(
    host_name: str,
    spec: GpuSpec,
    sku: str,
    gpu_seconds: float,
    region: str = "eastus",
    pricing: PricingModel = DEFAULT_PRICING,
) -> dict[str, str]:
    """
    Generate a set of Azure tags with cost attribution data.

    These can be applied via Azure SDK, Azure Policy, or exported for tagging tools.
    """
    hourly_cost = calculate_gpu_hourly_cost(spec, sku, region, pricing)
    per_second = calculate_cost_per_second(spec, sku, region, pricing) or 0
    total_cost = estimate_cost_for_samples(gpu_seconds, spec, sku, region, pricing) or 0

    tags = {
        "avd_masters:monitored": "true",
        "avd_masters:gpu-model": spec.model,
        "avd_masters:gpu-count": str(spec.gpu_count),
        "avd_masters:sku": sku,
        "avd_masters:cost-model": pricing.name,
        "avd_masters:cost-per-hour": f"{hourly_cost:.4f}" if hourly_cost else "unknown",
        "avd_masters:cost-per-second": f"{per_second:.8f}",
        "avd_masters:total-cost-estimate": f"{total_cost:.4f}",
        "avd_masters:last-calculated": datetime.utcnow().isoformat(),
    }
    return tags


# =============================================================================
# Convenience
# =============================================================================

def get_cost_summary_for_host(
    host_name: str,
    spec: GpuSpec,
    sku: str,
    total_gpu_seconds: float,
    region: str = "eastus",
) -> dict:
    """Return a nice summary dict for reporting / API use."""
    return {
        "host": host_name,
        "sku": sku,
        "gpu_model": spec.model,
        "gpu_count": spec.gpu_count,
        "total_gpu_seconds": total_gpu_seconds,
        "estimated_cost_usd": estimate_cost_for_samples(total_gpu_seconds, spec, sku, region),
        "cost_per_second": calculate_cost_per_second(spec, sku, region),
        "cost_per_hour": calculate_gpu_hourly_cost(spec, sku, region),
    }


def auto_tag_host_with_live_sku(
    host_name: str,
    sku: str,
    gpu_seconds: float,
    region: str,
    compute_client=None,
) -> dict[str, str]:
    """
    Auto-tag a host using the freshest SKU data available.

    If a compute_client is provided, it will attempt to refresh SKU info for the region.
    """
    spec = lookup(sku)

    if compute_client and not spec:
        live = sku_discovery.fetch_gpu_skus_for_regions(compute_client, [region])
        if sku.lower() in live:
            spec = live[sku.lower()]

    if not spec:
        spec = GpuSpec("nvidia", "Unknown", 1.0, 0)

    return generate_cost_tags(host_name, spec, sku, gpu_seconds, region)
