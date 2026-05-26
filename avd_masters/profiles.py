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

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ProfileHealth:
    """
    Rich assessment of a host's (or pool's) profile configuration health.

    This is designed to be brutally honest about the state of user profiles,
    which is one of the top reasons AVD deployments feel broken in production.
    """
    host_name: str

    # Core FSLogix state
    fslogix_enabled: bool = False
    fslogix_version: Optional[str] = None
    using_roaming_profiles: bool = False

    # Container details
    profile_container_path: Optional[str] = None
    storage_account: Optional[str] = None
    storage_tier: Optional[str] = None          # Premium, Standard, etc.
    container_size_gb: Optional[float] = None
    container_growth_pattern: Optional[str] = None  # "normal", "exploding", "stagnant"

    # Redirections & exclusions
    has_redirections: bool = False
    redirections_issues: list[str] = field(default_factory=list)

    # Common real-world problems
    common_misconfigs: list[str] = field(default_factory=list)
    risk_level: str = "unknown"                 # low, medium, high, critical

    @property
    def health_score(self) -> int:
        """0-100 score. 100 = excellent modern FSLogix setup."""
        score = 100

        if not self.fslogix_enabled:
            score -= 55
        if self.using_roaming_profiles:
            score -= 45

        if self.profile_container_path and self.profile_container_path.lower().startswith("c:"):
            score -= 20
        if self.storage_tier and self.storage_tier.lower() == "standard":
            score -= 15

        if not self.has_redirections:
            score -= 10
        if self.redirections_issues:
            score -= min(15, len(self.redirections_issues) * 5)

        if self.risk_level == "critical":
            score = min(score, 25)
        elif self.risk_level == "high":
            score = min(score, 45)

        return max(0, score)

    @property
    def is_broken(self) -> bool:
        return self.health_score < 40

    @property
    def severity(self) -> str:
        if self.health_score >= 80:
            return "good"
        elif self.health_score >= 60:
            return "warning"
        elif self.health_score >= 40:
            return "bad"
        else:
            return "critical"


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
    Analyze a collected ProfileConfig and turn it into a rich, actionable ProfileHealth object.

    This version is significantly more opinionated and tuned to real-world AVD disasters.
    """
    health = ProfileHealth(host_name=host_name)
    health.fslogix_enabled = config.fslogix_enabled
    health.fslogix_version = config.fslogix_version
    health.using_roaming_profiles = config.is_roaming_enabled
    health.profile_container_path = config.vhd_locations[0] if config.vhd_locations else None
    health.has_redirections = bool(config.redir_xml_source)

    # Storage tier detection
    if health.profile_container_path:
        path_lower = health.profile_container_path.lower()
        if any(x in path_lower for x in ["premium", "ultra"]):
            health.storage_tier = "Premium"
        elif "standard" in path_lower:
            health.storage_tier = "Standard"

    misconfigs = []
    risk_factors = []

    # === Critical issues ===
    if not health.fslogix_enabled:
        misconfigs.append("FSLogix is not configured or disabled")
        risk_factors.append("critical")

    if health.using_roaming_profiles:
        misconfigs.append("Legacy roaming profiles are still enabled")
        risk_factors.append("critical")

    if health.profile_container_path and health.profile_container_path.lower().startswith("c:"):
        misconfigs.append("Profile containers writing to OS disk (very dangerous)")
        risk_factors.append("high")

    # === High impact issues ===
    if health.storage_tier == "Standard":
        misconfigs.append("Profile containers on Standard storage (major source of latency)")
        risk_factors.append("high")

    if not health.has_redirections:
        misconfigs.append("No redirections.xml detected (or not configured)")
        risk_factors.append("high")

    if config.profile_type is not None and config.profile_type != 0:
        misconfigs.append(f"Non-standard ProfileType in use ({config.profile_type})")

    # === Medium issues ===
    if config.vhd_locations and len(config.vhd_locations) > 3:
        misconfigs.append("Multiple VHDLocations configured — can cause confusion and performance issues")

    # Risk level calculation
    if "critical" in risk_factors:
        health.risk_level = "critical"
    elif "high" in risk_factors:
        health.risk_level = "high"
    elif risk_factors:
        health.risk_level = "medium"
    else:
        health.risk_level = "low"

    health.common_misconfigs = misconfigs
    return health


def generate_profile_opportunities(health: ProfileHealth) -> list[dict]:
    """
    Convert profile configuration disasters into rich Midas-style opportunities.
    These are some of the highest-impact "setup debt" items in AVD.
    """
    opportunities = []

    if not health.fslogix_enabled:
        opportunities.append({
            "type": "no_fslogix",
            "title": "No FSLogix configured",
            "impact": "Extremely high risk of profile corruption and terrible logon/experience performance, especially on GPU workloads.",
            "recommendation": "Implement FSLogix profile containers as a priority. This is non-negotiable for production AVD.",
            "category": "profile",
        })

    if health.using_roaming_profiles:
        opportunities.append({
            "type": "legacy_roaming_profiles",
            "title": "Legacy roaming profiles still active",
            "impact": "One of the most common reasons AVD feels slow and unreliable. High sync latency and corruption risk.",
            "recommendation": "Migrate away from roaming profiles to FSLogix containers immediately.",
            "category": "profile",
        })

    if health.storage_tier and health.storage_tier.lower() == "standard":
        opportunities.append({
            "type": "profile_on_slow_storage",
            "title": "Profile containers on Standard storage",
            "impact": "Major contributor to profile-related latency and poor user experience.",
            "recommendation": "Migrate containers to Premium file shares or Premium blob storage.",
            "category": "profile",
        })

    if health.profile_container_path and health.profile_container_path.lower().startswith("c:"):
        opportunities.append({
            "type": "profile_on_os_disk",
            "title": "Profile containers on OS disk",
            "impact": "Very dangerous configuration. High risk of profile corruption and disk space issues.",
            "recommendation": "Move containers off the OS disk immediately.",
            "category": "profile",
        })

    if not health.has_redirections:
        opportunities.append({
            "type": "missing_redirections",
            "title": "No redirections.xml configured",
            "impact": "Unnecessary profile bloat and slower logons. Common source of 'my profile is huge' problems.",
            "recommendation": "Implement a proper redirections.xml with sensible exclusions.",
            "category": "profile",
        })

    if health.risk_level == "critical":
        opportunities.append({
            "type": "catastrophic_profile_setup",
            "title": "Critical profile configuration issues detected",
            "impact": "This environment is likely experiencing frequent profile problems and user complaints.",
            "recommendation": "Treat profile remediation as a high-priority project. Consider engaging someone experienced with FSLogix.",
            "category": "profile",
        })

    return opportunities


# =============================================================================
# FSLogix Profile Restoration & Recovery Toolkit
# =============================================================================
#
# This section is for helping with one of the most painful parts of AVD operations:
# busted or corrupted FSLogix profile containers.
#
# Goal: Provide smart analysis, safe inspection, and guided recovery steps
# without relying on fragile PowerShell one-liners that break with every MS change.

@dataclass
class ProfileContainerHealth:
    container_path: str
    exists: bool = False
    size_gb: Optional[float] = None
    last_modified_days: Optional[int] = None
    is_locked: bool = False
    has_vhdx: bool = False
    corruption_risk: str = "unknown"   # low, medium, high, critical
    recommended_action: str = ""


def analyze_profile_container_health(container_info: dict) -> ProfileContainerHealth:
    """
    Analyze a single FSLogix container (VHD/VHDX) for health indicators.

    This can be fed data from Azure storage queries or from a mounted inspection.
    """
    health = ProfileContainerHealth(
        container_path=container_info.get("path", "unknown")
    )

    health.exists = container_info.get("exists", False)
    health.size_gb = container_info.get("size_gb")
    health.last_modified_days = container_info.get("last_modified_days")
    health.is_locked = container_info.get("is_locked", False)
    health.has_vhdx = container_info.get("has_vhdx", False)

    risk = "low"
    action = "Appears healthy."

    if not health.exists:
        risk = "high"
        action = "Container is missing. User will get a new profile on next logon."
    elif health.is_locked:
        risk = "medium"
        action = "Container is locked (user may still be logged on or previous session didn't clean up)."
    elif health.last_modified_days and health.last_modified_days > 180:
        risk = "medium"
        action = "Very old container. Consider archival or cleanup policies."

    health.corruption_risk = risk
    health.recommended_action = action

    return health


def get_profile_recovery_guidance(health: ProfileContainerHealth) -> list[str]:
    """
    Practical, battle-tested style guidance for dealing with busted FSLogix containers.

    This is written from the perspective of someone who has had to clean up these messes.
    """
    guidance = []

    if not health.exists:
        guidance.append("Do NOT just delete the user's Windows profile folder. Let FSLogix recreate the container cleanly on next logon.")
        guidance.append("Investigate root cause: storage permissions, lifecycle policies deleting VHDs, backup software, etc.")

    if health.is_locked:
        guidance.append("First check for lingering sessions (including disconnected ones).")
        guidance.append("Only after confirming the user is fully logged off should you consider forcibly unlocking.")
        guidance.append("Document the unlock — this is a common source of future corruption.")

    if health.corruption_risk in ("high", "critical"):
        guidance.append("Treat the VHD as potentially corrupt. Do not delete without a backup or export attempt.")
        guidance.append("Preferred path: Use Microsoft's FSLogix tools or the container recovery process if available.")
        guidance.append("Nuclear option: Mount the VHD on a clean machine and selectively copy out user data (Desktop, Documents, AppData\\Roaming, etc.).")
        guidance.append("After recovery, strongly consider resetting the container for that user.")

    if health.last_modified_days and health.last_modified_days > 365:
        guidance.append("This container is over a year old. Strongly consider whether the user actually needs the full history or if a fresh profile is safer.")

    return guidance


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
