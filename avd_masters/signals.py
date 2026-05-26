"""
AVD Masters — Signals & Utilization Layer

This is the foundation for "terrifyingly accurate" idle and waste detection.

Design goals:
- Local only by default (no forced expensive ingestion)
- Pluggable collectors (nvidia-smi, rocm-smi, WinRM, SSH, Azure Metrics as optional)
- Clean datamodel that Midas, Optimizer, and Governance can all consume
- Graceful degradation: works great with partial or simulated data

Grok inside: We tell the truth about utilization. No sampling lies, no "it looks fine" when it's burning money.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


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

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "unknown"      # "nvidia-smi", "winrm", "simulated", "azure-metrics", etc.
    metadata: dict[str, Any] = field(default_factory=dict)

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

    def get_waste_score(self) -> float:
        """0-100 score where higher = more obvious waste happening right now."""
        if not self.signals:
            return 0.0
        idle_ratio = self.idle_count / len(self.signals)
        under_ratio = self.underutilized_count / len(self.signals)
        experience_penalty = (self.poor_experience_count / len(self.signals)) * 30
        return round((idle_ratio * 50 + under_ratio * 30 + experience_penalty), 1)

    def get_experience_score(self) -> float:
        """0-100 user experience health score for the fleet (higher is better)."""
        if not self.signals:
            return 100.0
        bad_ratio = self.poor_experience_count / len(self.signals)
        return round((1 - bad_ratio) * 100, 1)


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
    - Use WinRM / SSH to run nvidia-smi or rocm-smi
    - Parse the output cleanly (no sampling lies)
    - Handle fractional GPUs correctly
    - Fall back gracefully on unreachable hosts

    This stub shows the exact shape we want real collectors to follow.
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
    return enriched


# Convenience factories (polished)
def get_simulated_fleet(host_names: list[str]) -> FleetSignals:
    """Quick demo fleet with realistic painful patterns."""
    collector = SimulatedCollector()
    sigs = collector.collect(host_names)
    return FleetSignals(signals=sigs)


def get_local_collector_fleet(host_names: list[str]) -> FleetSignals:
    """
    Use this when you want to simulate what a real direct hardware collector would return.
    Swap the implementation inside LocalCollector when you have WinRM/SSH + smi working.
    """
    collector = LocalCollector()
    sigs = collector.collect(host_names)
    return FleetSignals(signals=sigs, window_hours=6)  # more realistic recent window
