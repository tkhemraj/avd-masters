"""
GROKY 2.0 — Predictive Forecasting Engine (MEGA FEATURE)

This is the foundation for one of the most powerful enterprise capabilities:

**Predictive Cost & Utilization Forecasting**

What it will eventually do:
- Forecast GPU utilization and dollar cost 7 / 30 / 90 days into the future.
- Detect cost anomalies early ("this pool is on track to cost 40% more next month").
- Run "what-if" simulations.
- Provide confidence intervals.

Current status: High-quality scaffold with realistic stub logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class ForecastPoint:
    date: datetime
    predicted_gpu_util: float
    predicted_cost_usd: float
    lower_bound: float
    upper_bound: float
    confidence: float


@dataclass
class ForecastResult:
    host_or_pool: str
    generated_at: datetime
    horizon_days: int
    points: list[ForecastPoint]
    total_predicted_cost: float
    trend: str  # "increasing", "stable", "decreasing"
    anomaly_risk: str  # "low", "medium", "high"


def generate_cost_forecast(
    entity_name: str,
    historical_data: list[dict],
    horizon_days: int = 30,
) -> ForecastResult:
    """
    Future: Takes historical utilization + cost data and returns a forecast.

    For now this returns a realistic simulated forecast so the architecture
    and data shapes can be reviewed and extended.
    """
    now = datetime.utcnow()
    points = []
    base_cost = 180.0
    trend_factor = 1.012  # slight upward trend for demo

    for i in range(horizon_days):
        date = now + timedelta(days=i)
        growth = trend_factor ** i
        predicted_cost = round(base_cost * growth, 2)
        variance = predicted_cost * 0.12

        points.append(ForecastPoint(
            date=date,
            predicted_gpu_util=round(62 + (i * 0.4), 1),
            predicted_cost_usd=predicted_cost,
            lower_bound=round(predicted_cost - variance, 2),
            upper_bound=round(predicted_cost + variance, 2),
            confidence=0.82 if i < 14 else 0.65,
        ))

    total = sum(p.predicted_cost_usd for p in points)

    return ForecastResult(
        host_or_pool=entity_name,
        generated_at=now,
        horizon_days=horizon_days,
        points=points,
        total_predicted_cost=round(total, 2),
        trend="increasing",
        anomaly_risk="medium",
    )


def simulate_what_if(
    base_forecast: ForecastResult,
    change: dict[str, Any],
) -> dict[str, Any]:
    """
    Simulate the impact of a change (e.g. adding hosts, changing SKU mix).
    """
    multiplier = change.get("utilization_change", 1.0)
    new_total = round(base_forecast.total_predicted_cost * multiplier, 2)
    savings = round(base_forecast.total_predicted_cost - new_total, 2)

    return {
        "scenario": change.get("description", "Custom scenario"),
        "original_forecast": base_forecast.total_predicted_cost,
        "new_forecast": new_total,
        "estimated_savings": savings,
        "recommendation": "This change looks favorable" if savings > 0 else "Review before proceeding",
    }
