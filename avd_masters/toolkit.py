"""
AVD Masters — Operator Toolkit

This is the practical toolkit layer for people who actually have to run AVD (especially
GPU AVD) in production and are tired of the platform feeling fragile and opaque.

Design principles (explicitly requested):
- Python + Azure SDK first. We do as much as possible from the control plane.
- Minimal reliance on PowerShell / WinRM where possible (Microsoft changes things too fast).
- When we need host data, prefer stable direct commands (nvidia-smi, etc.).
- Focus ruthlessly on the real problems that make AVD suck for operators and users:
  - Catastrophic profile/FSLogix setups
  - Terrible autoscale that doesn't consider user experience
  - Image and configuration drift
  - Invisible waste (cost + experience)
  - Orphaned and messy resources
  - Lack of defensible operational data

This module contains higher-level "do useful things" functions that operators can use
directly or that feed into Midas, CLI commands, and reporting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Profile Container Analysis (Azure-side, no PowerShell required)
# =============================================================================

@dataclass
class ProfileStorageAnalysis:
    """
    Analysis of FSLogix / profile storage from the Azure management plane.

    This is one of the highest-ROI things we can do without logging into VMs.
    We can detect many classic "people fucked up their profiles" situations by
    looking at the actual storage resources.
    """
    storage_account: str
    share_or_container: str
    performance_tier: str          # Premium, Standard, etc.
    estimated_vhd_count: int
    total_size_gb: float
    avg_vhd_size_gb: float
    oldest_vhd_age_days: Optional[int] = None
    likely_fslogix: bool = False
    red_flags: list[str] = None


def analyze_profile_storage(
    storage_account_name: str,
    share_or_container_name: str,
    credential,
    subscription_id: str,
) -> ProfileStorageAnalysis:
    """
    Analyze a storage account / share that is (or should be) used for FSLogix profile containers.

    This function works entirely from the Azure control plane. No WinRM, no PowerShell.

    What we can detect:
    - Whether the backing storage is Premium or Standard (huge for latency)
    - Rough number and size distribution of VHDs (can infer if it's actually being used as FSLogix storage)
    - Signs of profile sprawl or abandoned containers

    In a real implementation this would use:
    - azure.mgmt.storage.StorageManagementClient
    - Or azure.storage.filedatalake / blob client for deeper inspection

    For now this returns a realistic simulated result so the rest of the toolkit can be wired.
    """
    # TODO: Replace with real Azure SDK calls against the storage account.
    # We can list files, get properties, check SKU/tier, etc.

    analysis = ProfileStorageAnalysis(
        storage_account=storage_account_name,
        share_or_container=share_or_container_name,
        performance_tier="Standard",   # Common bad default
        estimated_vhd_count=847,
        total_size_gb=1240.5,
        avg_vhd_size_gb=1.46,
        oldest_vhd_age_days=420,
        likely_fslogix=True,
        red_flags=[
            "Storage tier is Standard (high latency for profile operations)",
            "Very old containers still present (possible abandoned user data)",
            "High number of small VHDs — possible sign of many lightly used or test accounts",
        ]
    )
    return analysis


def generate_profile_storage_recommendations(analysis: ProfileStorageAnalysis) -> list[str]:
    """Turn storage analysis into clear, actionable recommendations."""
    recs = []

    if analysis.performance_tier.lower() == "standard":
        recs.append(
            "Move profile containers to Premium file shares or Premium blob storage. "
            "Standard storage is one of the most common causes of 'AVD feels slow' complaints."
        )

    if analysis.oldest_vhd_age_days and analysis.oldest_vhd_age_days > 180:
        recs.append(
            f"You have containers that are {analysis.oldest_vhd_age_days}+ days old. "
            "Consider implementing a proper FSLogix cleanup / retention policy."
        )

    if analysis.estimated_vhd_count > 500 and analysis.avg_vhd_size_gb < 2:
        recs.append(
            "You have a very large number of tiny profile containers. "
            "This is often a sign of poor FSLogix configuration or many short-lived / test users."
        )

    return recs


# =============================================================================
# 1. Host Pool Intelligence (Autoscale that doesn't suck)
# =============================================================================

@dataclass
class HostPoolRecommendation:
    host_pool_name: str
    current_autoscale_enabled: bool
    recommended_min: int
    recommended_max: int
    reasoning: str
    estimated_monthly_savings: Optional[float] = None
    expected_experience_impact: str = "neutral"   # "better", "neutral", "worse"


def analyze_host_pool_autoscale(
    host_pool_name: str,
    current_usage: dict[str, Any],
    experience_metrics: dict[str, float],
) -> HostPoolRecommendation:
    """
    Given real usage + experience data, recommend sane autoscale settings.

    This is the kind of thing that actually helps people who don't know how to tune AVD.
    """
    avg_util = current_usage.get("avg_gpu_util", 50)
    p95_latency = experience_metrics.get("p95_input_latency_ms", 60)
    peak_sessions = current_usage.get("peak_sessions_last_7d", 10)

    recommended_min = max(1, int(peak_sessions * 0.6))
    recommended_max = max(recommended_min + 3, int(peak_sessions * 1.4))

    reasoning = []
    if avg_util > 75 and p95_latency > 80:
        reasoning.append("High utilization + poor experience → scale out more aggressively")
        recommended_max = int(recommended_max * 1.3)
    elif avg_util < 35:
        reasoning.append("Low utilization → can safely reduce maximum to save cost")
        recommended_max = max(recommended_min + 2, int(recommended_max * 0.75))

    return HostPoolRecommendation(
        host_pool_name=host_pool_name,
        current_autoscale_enabled=current_usage.get("autoscale_enabled", False),
        recommended_min=recommended_min,
        recommended_max=recommended_max,
        reasoning="; ".join(reasoning) or "Based on observed 7-day patterns",
        expected_experience_impact="better" if p95_latency > 70 else "neutral",
    )


# =============================================================================
# 2. Image & Configuration Drift Detection
# =============================================================================

@dataclass
class DriftReport:
    host_pool: str
    unique_images: int
    unique_gpu_driver_versions: int
    hosts_with_drift: list[str]
    severity: str   # "ok", "warning", "critical"


def detect_image_and_driver_drift(
    hosts: list[dict[str, Any]]
) -> list[DriftReport]:
    """
    Finds when hosts in the same logical pool are running different images or drivers.
    This is a very common source of "it works on some machines but not others".
    """
    from collections import defaultdict

    by_pool: dict[str, list] = defaultdict(list)
    for h in hosts:
        by_pool[h.get("host_pool", "unknown")].append(h)

    reports = []
    for pool, hlist in by_pool.items():
        images = {h.get("image_version") for h in hlist if h.get("image_version")}
        drivers = {h.get("gpu_driver_version") for h in hlist if h.get("gpu_driver_version")}

        drifted = []
        if len(images) > 1:
            drifted.extend([h["name"] for h in hlist])
        if len(drivers) > 1:
            drifted.extend([h["name"] for h in hlist])

        severity = "ok"
        if len(images) > 1 or len(drivers) > 1:
            severity = "warning" if len(images) + len(drivers) <= 3 else "critical"

        reports.append(DriftReport(
            host_pool=pool,
            unique_images=len(images),
            unique_gpu_driver_versions=len(drivers),
            hosts_with_drift=list(set(drifted)),
            severity=severity,
        ))

    return reports


# =============================================================================
# 3. Orphaned / Zombie Resource Hunter (very common mess)
# =============================================================================

@dataclass
class OrphanedResource:
    resource_id: str
    resource_type: str
    age_days: int
    estimated_monthly_cost: float
    reason: str


def find_likely_orphaned_resources(resources: list[dict]) -> list[OrphanedResource]:
    """
    Finds disks, snapshots, storage accounts, and old FSLogix VHDs that are probably abandoned.
    Pure Azure SDK work — no host access needed.
    """
    orphans = []
    now = datetime.now(timezone.utc)

    for r in resources:
        created = r.get("created_date")
        if not created:
            continue

        age = (now - created).days
        if age < 60:
            continue

        rtype = r.get("type", "")
        cost = r.get("estimated_monthly_cost", 0)

        reason = ""
        if "disk" in rtype.lower() and not r.get("attached_to_vm"):
            reason = "Unattached managed disk (classic orphan)"
        elif "snapshot" in rtype.lower() and age > 120:
            reason = "Old snapshot with no recent use"
        elif "storage" in rtype.lower() and r.get("last_modified_days", 0) > 200:
            reason = "Storage account with no recent activity"

        if reason:
            orphans.append(OrphanedResource(
                resource_id=r["id"],
                resource_type=rtype,
                age_days=age,
                estimated_monthly_cost=cost,
                reason=reason,
            ))

    return orphans


# =============================================================================
# 4. Quick Experience Health Snapshot (for operators)
# =============================================================================

def quick_avd_health_check(
    hosts: list[dict],
    signals: list[dict],
) -> dict[str, Any]:
    """
    One function operators can call to get a brutally honest snapshot of their environment.
    Great for "what the hell is going on in this tenant?" moments.
    """
    total = len(hosts)
    if total == 0:
        return {"status": "no_hosts_found"}

    poor_experience = sum(1 for s in signals if s.get("has_poor_experience"))
    high_cost_low_value = sum(1 for h in hosts if h.get("monthly_cost", 0) > 1500 and h.get("avg_util", 100) < 30)

    return {
        "total_hosts": total,
        "hosts_with_poor_experience": poor_experience,
        "experience_health_pct": round((1 - poor_experience / total) * 100, 1),
        "expensive_but_idle": high_cost_low_value,
        "summary": f"{poor_experience} hosts delivering bad experience. {high_cost_low_value} expensive hosts doing very little.",
    }


__all__ = [
    "ProfileStorageAnalysis",
    "analyze_profile_storage",
    "generate_profile_storage_recommendations",
    "HostPoolRecommendation",
    "analyze_host_pool_autoscale",
    "DriftReport",
    "detect_image_and_driver_drift",
    "OrphanedResource",
    "find_likely_orphaned_resources",
    "quick_avd_health_check",
]
