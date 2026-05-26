"""
GROKY 2.0 — Real Alerting & Management Engine

This is the practical heart that turns GROKY from "pretty monitoring" into something that actually helps you manage your GPU shit.

Core responsibilities:
- Evaluate current state against rules
- Fire meaningful alerts with context and recommended actions
- Tie into cost, forecasting, and optimizer modules
- Be actionable (not just "utilization is high")

Design goals:
- Simple to extend with new rules
- Rich context (cost impact, recommendations, etc.)
- Multiple output formats (console, JSON, webhooks later)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """A single actionable alert."""
    id: str
    severity: Severity
    title: str
    description: str
    resource: str
    metric: str
    value: float
    threshold: float
    impact: str | None = None          # e.g. "$420/month extra cost"
    recommendation: str | None = None  # actionable next step
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "resource": self.resource,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "impact": self.impact,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }

    def __str__(self) -> str:
        icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🔥"}[self.severity.value]
        return (
            f"{icon} [{self.severity.upper()}] {self.title}\n"
            f"   Resource: {self.resource}\n"
            f"   {self.metric}: {self.value} (threshold: {self.threshold})\n"
            f"   Impact: {self.impact or 'N/A'}\n"
            f"   → {self.recommendation or 'No recommendation yet'}"
        )


class AlertEngine:
    """
    The actual engine that evaluates data and fires alerts.
    """

    def __init__(self):
        self._rules: list[Callable] = []
        self._alerts: list[Alert] = []

    def add_rule(self, rule_func: Callable[[dict], Alert | None]):
        """Register a new alerting rule."""
        self._rules.append(rule_func)

    def evaluate(self, context: dict) -> list[Alert]:
        """
        Run all rules against the current context and return fired alerts.

        Context example:
        {
            "host_name": "...",
            "gpu_util_avg": 87.3,
            "imbalance_score": 52.0,
            "daily_cost": 1240.0,
            "forecast_next_30d": 48000,
            ...
        }
        """
        new_alerts = []
        for rule in self._rules:
            try:
                alert = rule(context)
                if alert:
                    new_alerts.append(alert)
                    self._alerts.append(alert)
            except Exception as e:
                # Never let one bad rule break the whole engine
                print(f"[AlertEngine] Rule failed: {e}")

        return new_alerts

    def get_alerts(self, severity: Severity | None = None) -> list[Alert]:
        if severity:
            return [a for a in self._alerts if a.severity == severity]
        return list(self._alerts)

    def clear(self):
        self._alerts.clear()


# =============================================================================
# Built-in Rules (these are the ones that actually help you manage)
# =============================================================================

def rule_high_gpu_utilization(context: dict) -> Alert | None:
    """Fire when average GPU utilization is critically high."""
    util = context.get("gpu_util_avg")
    if util is not None and util >= 90:
        return Alert(
            id=f"high-util-{context.get('host_name', 'unknown')}",
            severity=Severity.CRITICAL,
            title="Critical GPU Saturation",
            description=f"Host is running at {util}% average GPU utilization.",
            resource=context.get("host_name", "unknown"),
            metric="gpu_util_avg",
            value=util,
            threshold=90,
            impact="Risk of user experience degradation + potential throttling",
            recommendation="Consider adding capacity or rebalancing workloads immediately.",
        )
    elif util is not None and util >= 75:
        return Alert(
            id=f"high-util-warning-{context.get('host_name', 'unknown')}",
            severity=Severity.WARNING,
            title="High GPU Utilization",
            description=f"Host GPU utilization at {util}%.",
            resource=context.get("host_name", "unknown"),
            metric="gpu_util_avg",
            value=util,
            threshold=75,
            impact="Approaching performance cliff",
            recommendation="Monitor closely. Plan capacity increase.",
        )
    return None


def rule_high_cost_burn(context: dict) -> Alert | None:
    """Alert on expensive daily burn rate."""
    daily_cost = context.get("daily_cost_usd")
    if daily_cost is not None and daily_cost > 800:
        return Alert(
            id=f"high-cost-{context.get('host_name', 'unknown')}",
            severity=Severity.WARNING,
            title="High Daily Cost Burn",
            description=f"This host/pool is burning ~${daily_cost:.0f} per day.",
            resource=context.get("host_name", "unknown"),
            metric="daily_cost_usd",
            value=daily_cost,
            threshold=800,
            impact=f"~${daily_cost * 30:.0f} per month at current rate",
            recommendation="Review for optimization opportunities or right-sizing.",
        )
    return None


def rule_severe_imbalance(context: dict) -> Alert | None:
    """Fire on bad pool imbalance (the original killer feature)."""
    score = context.get("imbalance_score")
    if score is not None and score >= 50:
        return Alert(
            id=f"imbalance-critical-{context.get('pool_name', 'unknown')}",
            severity=Severity.CRITICAL,
            title="Severe Pool Imbalance",
            description=f"Pool imbalance score is {score}. Workloads are very unevenly distributed.",
            resource=context.get("pool_name", "unknown"),
            metric="imbalance_score",
            value=score,
            threshold=50,
            impact="Wasted capacity + inconsistent user experience",
            recommendation="Rebalance workloads or adjust session placement logic.",
        )
    elif score is not None and score >= 35:
        return Alert(
            id=f"imbalance-warning-{context.get('pool_name', 'unknown')}",
            severity=Severity.WARNING,
            title="Moderate Pool Imbalance",
            description=f"Pool imbalance score is {score}.",
            resource=context.get("pool_name", "unknown"),
            metric="imbalance_score",
            value=score,
            threshold=35,
            impact="Suboptimal resource usage",
            recommendation="Consider rebalancing soon.",
        )
    return None


def rule_forecast_overrun(context: dict) -> Alert | None:
    """Alert when forecasting predicts major cost overrun."""
    forecast = context.get("forecast_next_30d_cost")
    baseline = context.get("baseline_monthly_cost")
    if forecast and baseline and forecast > baseline * 1.4:
        overrun = forecast - baseline
        return Alert(
            id=f"forecast-overrun-{context.get('entity', 'unknown')}",
            severity=Severity.WARNING,
            title="Projected Cost Overrun",
            description=f"Current trends predict ${forecast:,.0f} next 30 days vs baseline ${baseline:,.0f}.",
            resource=context.get("entity", "unknown"),
            metric="forecast_next_30d_cost",
            value=forecast,
            threshold=baseline * 1.4,
            impact=f"+${overrun:,.0f} projected overrun",
            recommendation="Investigate utilization trends or apply optimization recommendations now.",
        )
    return None


# =============================================================================
# Default Engine Factory
# =============================================================================

def create_default_alert_engine() -> AlertEngine:
    """Returns an AlertEngine pre-loaded with the most useful rules."""
    engine = AlertEngine()
    engine.add_rule(rule_high_gpu_utilization)
    engine.add_rule(rule_high_cost_burn)
    engine.add_rule(rule_severe_imbalance)
    engine.add_rule(rule_forecast_overrun)
    return engine
