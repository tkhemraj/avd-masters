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
    """A single point-in-time or aggregated signal for one session host."""
    host_name: str
    gpu_util_avg: float          # 0-100
    gpu_util_peak: float | None = None
    memory_util_avg: float | None = None
    gpu_seconds_in_window: float = 0.0
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

    def get_waste_score(self) -> float:
        """0-100 score where higher = more obvious waste happening right now."""
        if not self.signals:
            return 0.0
        idle_ratio = self.idle_count / len(self.signals)
        under_ratio = self.underutilized_count / len(self.signals)
        return round((idle_ratio * 60 + under_ratio * 40), 1)


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
            # Simulate realistic painful patterns
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


# =============================================================================
# High-Value Local Analysis (Midas-grade)
# =============================================================================

def analyze_for_midas(fleet: FleetSignals) -> dict[str, Any]:
    """
    Turns raw signals into the kind of brutal, dollar-aware insights Midas loves.
    This is what lets Midas say "this host is actually idle" with confidence.
    """
    waste_score = fleet.get_waste_score()

    insights = {
        "waste_score": waste_score,
        "idle_hosts": [s.host_name for s in fleet.signals if s.is_likely_idle],
        "underutilized_hosts": [s.host_name for s in fleet.signals if s.is_underutilized and not s.is_likely_idle],
        "summary": "",
    }

    if waste_score > 55:
        insights["summary"] = (
            f"Fleet is leaking badly (waste score {waste_score}). "
            f"{fleet.idle_count} hosts are basically idle. This is the kind of thing that makes finance teams ask uncomfortable questions."
        )
    elif waste_score > 30:
        insights["summary"] = (
            f"Noticeable waste (waste score {waste_score}). "
            f"{fleet.underutilized_count} hosts are running well below what their hardware costs."
        )
    else:
        insights["summary"] = "Fleet looks reasonably utilized. Still worth a Midas pass for right-sizing and packing opportunities."

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


# Convenience factory
def get_simulated_fleet(host_names: list[str]) -> FleetSignals:
    collector = SimulatedCollector()
    signals = collector.collect(host_names)
    return FleetSignals(signals=signals)
