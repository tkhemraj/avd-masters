#!/usr/bin/env python3
"""
AVD Masters — "Help Me Manage My Shit" Demo

This is the kind of thing you actually run when you care about your AVD GPU environment.

It simulates a real management session:
- Loads current state of hosts/pools
- Runs analysis (utilization, cost, imbalance, forecasting)
- Fires real actionable alerts
- Shows optimization recommendations
- Gives you a clear "what should I do next" view

Run with:
    python examples/manage_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from avd_masters import alerting, catalog, cost, forecasting, optimizer


def create_sample_contexts():
    """Fake but realistic data representing your environment right now."""
    return [
        {
            "type": "host",
            "host_name": "avd-h100-prod-03",
            "gpu_util_avg": 94.2,
            "daily_cost_usd": 920.0,
            "imbalance_score": 28.0,
        },
        {
            "type": "pool",
            "pool_name": "prod-gpu-east-h100",
            "imbalance_score": 57.0,
            "gpu_util_avg": 41.0,
            "daily_cost_usd": 1240.0,
            "forecast_next_30d_cost": 52000,
            "baseline_monthly_cost": 31000,
        },
        {
            "type": "host",
            "host_name": "avd-fract-h100-12",
            "gpu_util_avg": 19.0,
            "daily_cost_usd": 310.0,
            "imbalance_score": 12.0,
        },
    ]


def main():
    print("\n" + "=" * 80)
    print("AVD Masters — Management Session".center(80))
    print("Helping you actually manage your GPU shit".center(80))
    print("=" * 80 + "\n")

    contexts = create_sample_contexts()
    engine = alerting.create_default_alert_engine()

    all_alerts = []
    all_recs = []

    for ctx in contexts:
        # Run alerting
        fired = engine.evaluate(ctx)

        # Also run forecasting on pools and feed interesting results into alerting
        if ctx.get("type") == "pool":
            forecast = forecasting.generate_cost_forecast(
                entity_name=ctx.get("pool_name", "unknown"),
                historical_data=[],
                horizon_days=30,
            )
            ctx["forecast_next_30d_cost"] = forecast.total_predicted_cost
            ctx["baseline_monthly_cost"] = ctx.get("daily_cost_usd", 0) * 30
            # Re-evaluate with forecast data
            extra_alerts = engine.evaluate(ctx)
            fired.extend(extra_alerts)
        all_alerts.extend(fired)

        # Try to generate placement recommendations
        if ctx.get("type") == "host" and ctx.get("gpu_util_avg", 0) < 30:
            rec = optimizer.recommend_placement(
                workload_name=ctx["host_name"],
                current_utilization={"avg_util": ctx["gpu_util_avg"]},
                available_pools=[],
            )
            if rec:
                all_recs.append(rec)

    # === Show Alerts ===
    print("🔥 ACTIVE ALERTS\n")
    if not all_alerts:
        print("No alerts fired. Everything looks calm (for now).\n")
    else:
        for alert in all_alerts:
            print(alert)
            print("-" * 80 + "\n")

    # === Show Recommendations ===
    print("💡 RECOMMENDATIONS\n")
    if not all_recs:
        print("No strong optimization recommendations right now.\n")
    else:
        for rec in all_recs:
            print(f"Workload: {rec.workload_name}")
            print(f"  Move from: {rec.current_pool} → {rec.recommended_pool} ({rec.recommended_sku})")
            print(f"  Estimated monthly savings: ${rec.estimated_monthly_savings:,.0f}")
            print(f"  Confidence: {rec.confidence * 100:.0f}%")
            print(f"  Reasoning: {rec.reasoning}\n")

    # === Summary ===
    critical = len([a for a in all_alerts if a.severity == alerting.Severity.CRITICAL])
    warnings = len([a for a in all_alerts if a.severity == alerting.Severity.WARNING])

    print("=" * 80)
    print(f"Session Summary: {len(all_alerts)} alerts ({critical} critical, {warnings} warnings)")
    if critical > 0:
        print("→ You have critical issues that need attention today.")
    elif warnings > 0:
        print("→ You have some things worth looking at this week.")
    else:
        print("→ Your environment looks healthy. Good job.")
    print("=" * 80 + "\n")

    print("This is the direction AVD Masters is going: real alerts + real recommendations you can act on.")
    print("Not just pretty charts.")


if __name__ == "__main__":
    main()
