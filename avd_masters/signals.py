"""
AVD Masters — Signals Layer

This is the central telemetry and observation layer for AVD Masters.

It is deliberately designed to be the single place where we bring together:
- GPU utilization & cost signals
- User experience / latency signals (frame times, input lag, etc.)
- Profile & FSLogix performance signals (one of the highest-impact areas in real AVD)

The goal is "terrifyingly accurate" visibility — not just utilization, but whether users are actually having a good (or terrible) experience, and whether the expensive hardware is being used effectively.

Design goals:
- Local first (direct collection via nvidia-smi/rocm-smi + WinRM/SSH)
- Pluggable collectors
- Clean, extensible datamodel that Midas, Governance, Alerting, and the Toolkit can all consume
- Graceful degradation with partial or simulated data

We don't just want to know if GPUs are busy. We want to know if the *experience* is good (including profile/FSLogix experience), and if the money is being well spent.

The model now uses composition (ProfileSignal inside HostSignal) for cleaner separation as profile pain became a first-class concern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProfileSignal:
    """
    Dedicated signal container for everything profile/FSLogix related.

    This exists because profile pain is so disproportionately bad in AVD that it
    deserves its own clean model instead of being buried in a giant flat HostSignal.
    """
    load_time_ms: float | None = None
    logon_duration_ms: float | None = None
    container_mount_latency_ms: float | None = None
    disk_latency_ms: float | None = None
    container_size_gb: float | None = None
    growth_rate_mb_per_day: float | None = None
    last_error_code: Optional[str] = None
    load_success_rate: float | None = None
    has_corruption_signals: bool = False

    @property
    def is_painful(self) -> bool:
        if self.load_time_ms and self.load_time_ms > 15000:
            return True
        if self.logon_duration_ms and self.logon_duration_ms > 45000:
            return True
        if self.has_corruption_signals:
            return True
        return False


@dataclass
class HostSignal:
    """
    The fundamental data unit in AVD Masters.

    A HostSignal represents a snapshot (or aggregated window) of everything that matters
    about a single AVD GPU session host — both from a cost/waste perspective and from
    a user experience perspective.

    This single model powers:
    - Cost attribution and Azure tagging
    - Midas intelligence (savings opportunities)
    - User Experience analysis (latency, frame times, "feels bad" detection)
    - Governance and CMMC reporting
    - Alerting

    Attributes
    ----------
    host_name : str
        Name of the session host.
    gpu_util_avg : float
        Average GPU utilization (0-100) over the collection window.
    gpu_util_peak : float, optional
        Peak utilization observed.
    memory_util_avg : float, optional
        Average GPU memory utilization.
    gpu_seconds_in_window : float
        Total GPU-seconds consumed in the window (used for consumption-based costing).

    Performance & Latency Fields (new in 2026)
    ------------------------------------------
    These fields allow AVD Masters to treat user experience as a first-class concern,
    not an afterthought.

    avg_frame_time_ms : float, optional
        Average time to render a frame on the GPU.
    p95_frame_time_ms : float, optional
        95th percentile frame time. This is the most important signal for perceived
        "jank" and stuttering. Values > ~33ms usually feel bad to users.
    input_latency_ms : float, optional
        End-to-end input-to-photon latency (ideal target is usually < 50-80ms for
        good interactive feel on graphics workloads).
    network_latency_ms : float, optional
        Network round-trip / protocol latency component.
    encoding_latency_ms : float, optional
        Time spent in GPU video encoding (relevant for certain AVD scenarios).

    Other Fields
    ------------
    timestamp : str
        ISO timestamp of the measurement.
    source : str
        Where the data came from (e.g. "local-direct", "simulated", "azure-metrics").
    metadata : dict
        Free-form additional context from the collector.

    Examples
    --------
    >>> signal = HostSignal(
    ...     host_name="avd-gpu-03",
    ...     gpu_util_avg=67.3,
    ...     p95_frame_time_ms=48.2,
    ...     input_latency_ms=112.0,
    ...     source="local-direct"
    ... )
    >>> signal.has_poor_experience
    True
    """

    host_name: str
    gpu_util_avg: float          # 0-100
    gpu_util_peak: float | None = None
    memory_util_avg: float | None = None
    gpu_seconds_in_window: float = 0.0

    # === Performance & Latency (the new frontier for AVD GPU excellence) ===
    avg_frame_time_ms: float | None = None          # Average GPU frame render time
    p95_frame_time_ms: float | None = None          # 95th percentile — critical for "jank"
    input_latency_ms: float | None = None           # End-to-end input to photon (ideal < 50-80ms for good feel)
    network_latency_ms: float | None = None         # Protocol / RTT latency (huge for remote graphics)
    encoding_latency_ms: float | None = None        # GPU encoding time if using video encoding

    # === Profile / FSLogix Experience Signals ===
    # Using composition for cleanliness — profile pain is a first-class citizen in AVD.
    profile: ProfileSignal = field(default_factory=ProfileSignal)

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "unknown"      # "nvidia-smi", "winrm", "simulated", "azure-metrics", etc.
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Clean serialization for APIs, storage, or reporting."""
        return {
            "host_name": self.host_name,
            "gpu_util_avg": self.gpu_util_avg,
            "gpu_util_peak": self.gpu_util_peak,
            "memory_util_avg": self.memory_util_avg,
            "profile": {
                "load_time_ms": self.profile.load_time_ms,
                "logon_duration_ms": self.profile.logon_duration_ms,
                "has_corruption_signals": self.profile.has_corruption_signals,
            },
            "timestamp": self.timestamp,
            "source": self.source,
        }

    @property
    def is_likely_idle(self) -> bool:
        """Heuristic: very low sustained utilization."""
        return self.gpu_util_avg < 15.0

    @property
    def is_underutilized(self) -> bool:
        """Heuristic: wasting expensive hardware."""
        return self.gpu_util_avg < 35.0

    @property
    def has_poor_experience(self) -> bool:
        """Heuristic for bad user experience (high frame time or input lag)."""
        if self.p95_frame_time_ms and self.p95_frame_time_ms > 33:  # ~30fps feels bad
            return True
        if self.input_latency_ms and self.input_latency_ms > 80:
            return True
        return False

    @property
    def has_poor_profile_experience(self) -> bool:
        """
        Heuristic specifically for bad profile/FSLogix performance.
        This is often the real hidden killer in AVD.
        """
        p = self.profile
        if p.load_time_ms and p.load_time_ms > 15000:
            return True
        if p.logon_duration_ms and p.logon_duration_ms > 45000:
            return True
        if p.container_mount_latency_ms and p.container_mount_latency_ms > 8000:
            return True
        if p.has_corruption_signals:
            return True
        if p.last_error_code:
            return True
        return False


@dataclass
class FleetSignals:
    """Aggregated signals across many hosts."""
    signals: list[HostSignal]
    window_hours: int = 24
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def idle_count(self) -> int:
        return sum(1 for s in self.signals if s.is_likely_idle)

    @property
    def underutilized_count(self) -> int:
        return sum(1 for s in self.signals if s.is_underutilized)

    @property
    def avg_util(self) -> float:
        if not self.signals:
            return 0.0
        return round(sum(s.gpu_util_avg for s in self.signals) / len(self.signals), 1)

    @property
    def poor_experience_count(self) -> int:
        return sum(1 for s in self.signals if s.has_poor_experience)

    @property
    def poor_profile_experience_count(self) -> int:
        return sum(1 for s in self.signals if s.has_poor_profile_experience)

    def get_waste_score(self) -> float:
        """0-100 score where higher = more obvious waste happening right now."""
        if not self.signals:
            return 0.0
        idle_ratio = self.idle_count / len(self.signals)
        under_ratio = self.underutilized_count / len(self.signals)
        experience_penalty = (self.poor_experience_count / len(self.signals)) * 30
        profile_penalty = (self.poor_profile_experience_count / len(self.signals)) * 25
        return round((idle_ratio * 45 + under_ratio * 25 + experience_penalty + profile_penalty), 1)

    def get_experience_score(self) -> float:
        """0-100 user experience health score for the fleet (higher is better)."""
        if not self.signals:
            return 100.0
        bad_ratio = self.poor_experience_count / len(self.signals)
        return round((1 - bad_ratio) * 100, 1)

    def get_profile_experience_score(self) -> float:
        """
        Dedicated score for profile/FSLogix experience health.
        This is often the real differentiator in whether users say AVD "sucks".
        """
        if not self.signals:
            return 100.0
        bad_ratio = self.poor_profile_experience_count / len(self.signals)
        return round((1 - bad_ratio) * 100, 1)

    def get_profile_debt_score(self) -> float:
        """
        0-100 score representing how much "profile technical debt" exists in the fleet.
        Higher = more painful profile setups that are actively hurting users and costing money.
        """
        if not self.signals:
            return 0.0

        debt = 0.0
        for sig in self.signals:
            if sig.has_poor_profile_experience:
                debt += 40
            if sig.profile.has_corruption_signals:
                debt += 35
            if sig.profile.load_time_ms and sig.profile.load_time_ms > 30000:
                debt += 20
            if sig.profile.last_error_code:
                debt += 25

        # Normalize
        max_possible = len(self.signals) * 120
        return round(min(100, (debt / max_possible) * 100), 1)

    def to_dict(self) -> dict:
        """Serialize the entire fleet for storage or APIs."""
        return {
            "generated_at": self.generated_at,
            "window_hours": self.window_hours,
            "signals": [s.to_dict() for s in self.signals],
        }


# =============================================================================
# Collection Interface (pluggable)
# =============================================================================

class SignalCollector:
    """Base class for all collectors. Implement .collect() for real sources."""

    name: str = "base"

    def collect(self, hosts: list[str], **kwargs) -> list[HostSignal]:
        raise NotImplementedError


class SimulatedCollector(SignalCollector):
    """Useful for demos, testing, and when you don't have live access yet."""
    name = "simulated"

    def collect(self, hosts: list[str], **kwargs) -> list[HostSignal]:
        signals = []
        for i, name in enumerate(hosts):
            # Simulate realistic painful patterns seen in real AVD GPU fleets
            if "h100" in name.lower() or "mi300" in name.lower():
                util = 12.0 if i % 3 == 0 else (28.0 if i % 2 == 0 else 67.0)
            else:
                util = 45.0 + (i * 7) % 35

            signals.append(HostSignal(
                host_name=name,
                gpu_util_avg=round(util, 1),
                gpu_util_peak=round(min(100, util + 25), 1),
                source="simulated",
                metadata={"note": "demo data — replace with real collector"},
            ))
        return signals


class LocalCollector(SignalCollector):
    """
    Realistic pattern for direct hardware collection.

    In production this would:
    - Use WinRM / SSH to run nvidia-smi or rocm-smi for GPU metrics
    - Collect custom latency/experience probes
    - Collect profile/FSLogix performance data (logon times, container mount latency, etc.)
    - Parse everything cleanly with no sampling lies
    - Handle fractional GPUs correctly
    - Fall back gracefully on unreachable hosts

    This stub shows the exact shape we want real collectors to follow.
    Real implementations should be able to populate all fields on HostSignal, including the profile experience fields.
    """
    name = "local-direct"

    def collect(self, hosts: list[str], **kwargs) -> list[HostSignal]:
        """
        Placeholder for real local collection.
        Replace the body with actual WinRM/SSH + smi parsing when ready.
        """
        # For now we return slightly better simulated data to prove the path
        signals = []
        for i, name in enumerate(hosts):
            # More realistic distribution for a "mature but messy" fleet
            if any(x in name.lower() for x in ["h100", "h200", "mi300"]):
                util = 8.5 if i % 4 == 0 else (19.0 if i % 3 == 0 else 52.0)
            else:
                util = 31.0 + ((i * 11) % 48)

            # Simulate realistic latency patterns alongside utilization
            frame_time = 16 + (i % 5) * 8 if util < 70 else 45 + (i % 7) * 10
            input_lag = 35 + (i % 4) * 15

            signals.append(HostSignal(
                host_name=name,
                gpu_util_avg=round(util, 1),
                gpu_util_peak=round(min(100, util * 1.4), 1),
                avg_frame_time_ms=round(frame_time, 1),
                p95_frame_time_ms=round(frame_time * 1.6, 1),
                input_latency_ms=round(input_lag, 1),
                source=self.name,
                metadata={
                    "collector_version": "0.3-local",
                    "note": "Replace with real collection: nvidia-smi + custom latency probes via WinRM/SSH"
                },
            ))
        return signals


# =============================================================================
# High-Value Local Analysis (Midas-grade)
# =============================================================================

def analyze_for_midas(fleet: FleetSignals) -> dict[str, Any]:
    """
    Turns raw signals into the kind of brutal, dollar-aware insights Midas loves.
    This is what lets Midas say "this host is actually idle" with confidence.
    """
    waste_score = fleet.get_waste_score()

    idle = [s for s in fleet.signals if s.is_likely_idle]
    under = [s for s in fleet.signals if s.is_underutilized and not s.is_likely_idle]

    insights = {
        "waste_score": waste_score,
        "idle_hosts": [s.host_name for s in idle],
        "underutilized_hosts": [s.host_name for s in under],
        "avg_util": fleet.avg_util,
        "summary": "",
    }

    experience_score = fleet.get_experience_score()
    bad_experience = fleet.poor_experience_count

    if waste_score > 60:
        insights["summary"] = (
            f"This fleet is bleeding money (waste score {waste_score}). "
            f"{len(idle)} hosts are basically doing nothing. Someone is going to notice the bill eventually."
        )
    elif waste_score > 35:
        insights["summary"] = (
            f"Clear waste (waste score {waste_score}). "
            f"{len(under)} hosts are running well below the cost of the metal they're sitting on."
        )
    else:
        insights["summary"] = (
            f"Fleet utilization is acceptable ({fleet.avg_util}% avg). "
            "Still run Midas — there are almost always right-sizing and packing opportunities hiding in the noise."
        )

    if bad_experience > 0:
        insights["summary"] += (
            f" Additionally, {bad_experience} hosts are delivering poor user experience "
            f"(experience score: {experience_score}). Expensive hardware that feels bad is the most painful kind of waste."
        )

    profile_bad = fleet.poor_profile_experience_count
    profile_score = fleet.get_profile_experience_score()
    if profile_bad > 0:
        insights["summary"] += (
            f" Profile/FSLogix experience is also suffering on {profile_bad} hosts "
            f"(profile experience score: {profile_score}). This is frequently the real hidden root cause of 'AVD sucks' complaints."
        )

    return insights


def enrich_midas_opportunities(hosts: list[Any], fleet_signals: FleetSignals | None = None) -> list[dict]:
    """
    When we have real signals, we can turn generic opportunities into terrifyingly specific ones.
    This is the bridge between discovery + Midas and real utilization truth.
    """
    enriched = []
    if not fleet_signals:
        return enriched

    signal_map = {s.host_name: s for s in fleet_signals.signals}

    for host in hosts:
        name = getattr(host, "name", str(host))
        sig = signal_map.get(name)
        if sig and sig.is_likely_idle:
            enriched.append({
                "host": name,
                "type": "confirmed_idle",
                "util": sig.gpu_util_avg,
                "grok_line": f"{name} has been at {sig.gpu_util_avg:.1f}% for the window. This is not 'bursty'. This is expensive sleep.",
            })
        if sig and sig.has_poor_profile_experience:
            reasons = []
            p = sig.profile
            if p.load_time_ms and p.load_time_ms > 15000:
                reasons.append(f"slow profile load ({int(p.load_time_ms/1000)}s)")
            if p.logon_duration_ms and p.logon_duration_ms > 45000:
                reasons.append(f"painful logon ({int(p.logon_duration_ms/1000)}s)")
            if p.has_corruption_signals:
                reasons.append("signs of profile corruption")

            enriched.append({
                "host": name,
                "type": "poor_profile_performance",
                "grok_line": (
                    f"{name} has terrible profile/FSLogix performance ({', '.join(reasons)}). "
                    "This is one of the most common (and expensive) reasons users say AVD feels broken."
                ),
            })
    return enriched


# Convenience factories (polished)
def get_simulated_fleet(host_names: list[str]) -> FleetSignals:
    """Quick demo fleet with realistic painful patterns (util + latency + profile experience)."""
    collector = SimulatedCollector()
    sigs = collector.collect(host_names)
    return FleetSignals(signals=sigs)


def get_local_collector_fleet(host_names: list[str]) -> FleetSignals:
    """
    Use this when you want to simulate what a real direct hardware collector would return.

    In production you would replace the body of LocalCollector.collect() with actual
    WinRM/SSH execution that gathers:
    - nvidia-smi / rocm-smi data
    - Custom latency probes
    - Profile/FSLogix performance metrics (very high value)

    This is the recommended entry point for most real usage today.
    """
    collector = LocalCollector()
    sigs = collector.collect(host_names)
    return FleetSignals(signals=sigs, window_hours=6)  # more realistic recent window


def get_combined_fleet_health(fleet: FleetSignals) -> dict[str, float]:
    """
    Returns a compact health dashboard for the fleet.

    Useful for quick operator views or feeding into Midas/Governance.
    """
    return {
        "waste_score": fleet.get_waste_score(),
        "overall_experience_score": fleet.get_experience_score(),
        "profile_experience_score": fleet.get_profile_experience_score(),
        "poor_experience_hosts": fleet.poor_experience_count,
        "poor_profile_experience_hosts": fleet.poor_profile_experience_count,
        "idle_hosts": fleet.idle_count,
    }


def get_top_pain_points(fleet: FleetSignals, limit: int = 5) -> list[dict]:
    """
    Returns the hosts with the worst combined pain (cost waste + bad experience + profile issues).
    Extremely useful for prioritization.
    """
    scored = []
    for sig in fleet.signals:
        pain = 0.0
        if sig.is_likely_idle or sig.is_underutilized:
            pain += 30
        if sig.has_poor_experience:
            pain += 40
        if sig.has_poor_profile_experience:
            pain += 50
        if sig.profile.has_corruption_signals:
            pain += 35

        if pain > 0:
            scored.append({
                "host": sig.host_name,
                "pain_score": round(pain, 1),
                "reasons": {
                    "idle_or_underutilized": sig.is_likely_idle or sig.is_underutilized,
                    "poor_experience": sig.has_poor_experience,
                    "poor_profile_experience": sig.has_poor_profile_experience,
                    "profile_corruption": sig.profile.has_corruption_signals,
                }
            })

    return sorted(scored, key=lambda x: x["pain_score"], reverse=True)[:limit]

    def generate_profile_debt_opportunities(self) -> list[dict]:
        """
        Directly produces Midas-ready opportunity dicts focused on profile pain.
        This is rocket fuel for the intelligence engine.
        """
        opps = []
        for sig in self.signals:
            if not sig.has_poor_profile_experience:
                continue

            p = sig.profile
            pain_reasons = []
            if p.load_time_ms and p.load_time_ms > 15000:
                pain_reasons.append(f"slow container load ({int(p.load_time_ms/1000)}s)")
            if p.logon_duration_ms and p.logon_duration_ms > 45000:
                pain_reasons.append(f"terrible logon time ({int(p.logon_duration_ms/1000)}s)")
            if p.has_corruption_signals:
                pain_reasons.append("corruption signals detected")

            opps.append({
                "host": sig.host_name,
                "type": "profile_debt",
                "grok_line": f"{sig.host_name} is suffering from bad FSLogix/profile performance ({', '.join(pain_reasons)}). This is expensive and makes users hate life.",
                "impact": "Direct user experience destruction on expensive hardware.",
            })
        return opps
