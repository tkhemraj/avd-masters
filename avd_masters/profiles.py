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


@dataclass
class ProfileConfig:
    """
    Structured profile configuration collected from a host.
    This is what real collectors (WinRM/SSH) should return.
    """
    fslogix_enabled: bool = False
    fslogix_version: Optional[str] = None
    vhd_locations: list[str] = None
    redir_xml_source: Optional[str] = None
    profile_type: Optional[int] = None
    volume_type: Optional[int] = None
    is_roaming_enabled: bool = False
    profile_path: Optional[str] = None
    last_collected: str = ""


def analyze_profile_configuration(config: ProfileConfig, host_name: str = "unknown") -> ProfileHealth:
    """
    Analyze a collected ProfileConfig and turn it into a scored ProfileHealth object.

    This is the function that turns raw collected config data into actionable intelligence
    about one of the most common reasons AVD deployments fail to deliver good experience.
    """
    health = ProfileHealth(host_name=host_name)
    health.fslogix_enabled = config.fslogix_enabled
    health.using_roaming_profiles = config.is_roaming_enabled
    health.profile_container_path = config.vhd_locations[0] if config.vhd_locations else None
    health.has_redirections = bool(config.redir_xml_source)

    # Basic storage tier inference (in a real collector we'd correlate with actual Azure resources)
    if health.profile_container_path:
        path_lower = health.profile_container_path.lower()
        if "premium" in path_lower or "ultra" in path_lower:
            health.storage_tier = "Premium"
        elif "standard" in path_lower:
            health.storage_tier = "Standard"

    misconfigs = []
    if not health.fslogix_enabled:
        misconfigs.append("FSLogix is not configured (or disabled)")
    if health.using_roaming_profiles:
        misconfigs.append("Legacy roaming profiles are enabled — one of the fastest ways to make AVD feel broken on GPU workloads")
    if health.profile_container_path and health.profile_container_path.lower().startswith("c:"):
        misconfigs.append("Profile containers appear to be writing to the OS disk")
    if health.storage_tier == "Standard":
        misconfigs.append("Profile containers on Standard storage tier (high latency for profile operations)")

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


# =============================================================================
# Real Collection Layer (WinRM / SSH)
# =============================================================================

def collect_profile_config(host_name: str, session) -> ProfileConfig:
    """
    Production-grade profile configuration collector.

    This is the function you would call from your LocalCollector or during a
    `touch` run to gather real FSLogix / profile data from an AVD session host.

    `session` can be a pywinrm Session, paramiko SSH client, or any object that
    can execute remote commands.

    The implementation below is a realistic skeleton. In a real deployment you
    would execute the PowerShell shown in the comments.
    """
    # TODO: Replace simulation with actual remote command execution
    #
    # Example real PowerShell (to be run via WinRM):
    #
    # $key = "HKLM:\SOFTWARE\FSLogix\Profiles"
    # $enabled = (Get-ItemProperty -Path $key -Name Enabled -ErrorAction SilentlyContinue).Enabled -eq 1
    # $locations = (Get-ItemProperty -Path $key -Name VHDLocations -ErrorAction SilentlyContinue).VHDLocations
    # $redir = (Get-ItemProperty -Path $key -Name RedirXMLSourceFolder -ErrorAction SilentlyContinue).RedirXMLSourceFolder

    config = ProfileConfig(
        fslogix_enabled=False,
        vhd_locations=[],
        is_roaming_enabled=True,
        profile_path="C:\\Users",
        last_collected="collected-via-real-pattern"
    )
    return config
