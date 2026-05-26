"""
AVD Masters — Profile Management Intelligence

This module addresses one of the most common and painful reasons AVD "sucks" in real deployments:

People fuck up user profiles.

Common disasters we detect and call out:
- Using legacy roaming profiles instead of FSLogix
- Not using FSLogix at all on GPU workloads
- Storing profile containers on the wrong storage (premium vs standard, wrong region, wrong performance tier)
- Grossly undersized or oversized profile disks
- Missing redirections.xml or bad exclusions
- Profile containers on the OS disk or ephemeral storage

The goal is not just detection — it's turning these into clear, quantified "setup debt" opportunities inside Midas,
with both user experience impact and (often) cost impact.

This is part of making AVD Masters the tool that actually helps teams not shoot themselves in the foot during setup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ProfileHealth:
    """
    Assessment of a single host's profile configuration health.
    """
    host_name: str
    fslogix_enabled: bool = False
    using_roaming_profiles: bool = False
    profile_container_path: Optional[str] = None
    storage_tier: Optional[str] = None          # "Premium", "Standard", "Ultra", etc.
    container_size_gb: Optional[int] = None
    has_redirections: bool = False
    common_misconfigs: list[str] = None         # e.g. ["No FSLogix", "Profile on C: drive", ...]

    @property
    def health_score(self) -> int:
        """0-100 score. 100 = perfect modern setup."""
        score = 100
        if not self.fslogix_enabled:
            score -= 60
        if self.using_roaming_profiles:
            score -= 40
        if self.profile_container_path and self.profile_container_path.lower().startswith("c:"):
            score -= 25
        if not self.has_redirections:
            score -= 15
        return max(0, score)

    @property
    def is_broken(self) -> bool:
        return self.health_score < 50


def analyze_profile_configuration(host_data: dict) -> ProfileHealth:
    """
    Analyze profile-related configuration for a host.

    In a real implementation, `host_data` would come from:
    - Registry checks via WinRM/SSH (FSLogix keys under HKLM\\SOFTWARE\\FSLogix)
    - File system checks on profile container storage
    - Azure resource queries for the actual disk/file share backing the VHDs

    For now this is a stub that demonstrates the expected shape and common failure modes.
    """
    health = ProfileHealth(host_name=host_data.get("name", "unknown"))

    # Simulated detection logic (replace with real collection)
    profile_config = host_data.get("profile_config", {})

    health.fslogix_enabled = profile_config.get("fslogix_enabled", False)
    health.using_roaming_profiles = profile_config.get("roaming_profiles_enabled", False)
    health.profile_container_path = profile_config.get("container_path")
    health.storage_tier = profile_config.get("storage_tier")
    health.container_size_gb = profile_config.get("container_size_gb")
    health.has_redirections = profile_config.get("has_redirections_xml", False)

    misconfigs = []
    if not health.fslogix_enabled:
        misconfigs.append("FSLogix is not configured")
    if health.using_roaming_profiles:
        misconfigs.append("Legacy roaming profiles are enabled (very bad for AVD)")
    if health.profile_container_path and health.profile_container_path.lower().startswith("c:"):
        misconfigs.append("Profile containers appear to be on the OS disk")
    if health.storage_tier and health.storage_tier.lower() == "standard":
        misconfigs.append("Profile containers on Standard storage (high latency risk)")

    health.common_misconfigs = misconfigs
    return health


def generate_profile_opportunities(health: ProfileHealth) -> list[dict]:
    """
    Turn profile misconfigurations into Midas-style opportunities.
    These get fed into the intelligence engine.
    """
    opportunities = []

    if not health.fslogix_enabled:
        opportunities.append({
            "type": "no_fslogix",
            "title": "No FSLogix configured",
            "impact": "High risk of profile corruption, slow logons, and terrible user experience on GPU workloads.",
            "recommendation": "Migrate to FSLogix profile containers immediately. This is table stakes for any serious AVD deployment.",
        })

    if health.using_roaming_profiles:
        opportunities.append({
            "type": "legacy_roaming_profiles",
            "title": "Using legacy roaming profiles",
            "impact": "One of the fastest ways to make AVD feel broken. High latency, profile bloat, and sync issues.",
            "recommendation": "Disable roaming profiles and move to FSLogix containers. This is a top-5 AVD setup mistake.",
        })

    if health.storage_tier and health.storage_tier.lower() == "standard":
        opportunities.append({
            "type": "profile_on_slow_storage",
            "title": "Profile containers on Standard storage",
            "impact": "Users will experience high latency on profile operations, especially with GPU workloads.",
            "recommendation": "Move profile containers to Premium SSD or Azure Files Premium.",
        })

    return opportunities
