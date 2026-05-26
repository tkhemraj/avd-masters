"""
AVD Masters — Main Entry Point

This is the real command line interface for managing your AVD GPU environment.

Usage examples:
    python run.py                    # Show catalog + status
    python run.py alerts             # Run the management demo with alerts
    python run.py cost               # Show cost attribution demo
    python run.py forecast           # Show forecasting
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import avd_masters.catalog as catalog
from examples import manage_demo, finops_demo


def banner():
    print(r"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                           AVD Masters                                          ║
║                                                                              ║
║           Direct Hardware Truth for Azure Virtual Desktop                    ║
║                    No lies. No bills. Just silicon.                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
""".strip())


def cmd_status():
    banner()
    print("\nCatalog engaged. Modern reality loaded.\n")

    stats = catalog.summarize()
    print(f"  SKUs tracked:        {stats['total_skus']}")
    print(f"  NVIDIA:              {stats['nvidia']}")
    print(f"  AMD:                 {stats['amd']}")
    print(f"  Fractional SKUs:     {stats['fractional_skus']}")
    print(f"  Retiring SKUs:       {stats['retiring_skus']}")
    print()

    print("Run `python run.py alerts` to see real management alerts and recommendations.\n")


def cmd_alerts():
    print("Running management session with live alerting...\n")
    manage_demo.main()


def cmd_cost():
    print("Running FinOps cost attribution demo...\n")
    finops_demo.main()


def cmd_forecast():
    from avd_masters import forecasting

    print("Generating sample 30-day cost forecast...\n")
    result = forecasting.generate_cost_forecast(
        entity_name="prod-gpu-east-h100",
        historical_data=[],
        horizon_days=30,
    )
    print(f"Entity: {result.host_or_pool}")
    print(f"Trend: {result.trend}")
    print(f"30-day predicted cost: ${result.total_predicted_cost:,.2f}")
    print(f"Anomaly risk: {result.anomaly_risk}\n")


def main():
    parser = argparse.ArgumentParser(description="AVD Masters - GPU Management for AVD")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Show catalog and basic status")
    subparsers.add_parser("alerts", help="Run full management + alerting demo")
    subparsers.add_parser("cost", help="Run FinOps cost attribution demo")
    subparsers.add_parser("forecast", help="Show predictive forecasting demo")

    args = parser.parse_args()

    if args.command == "alerts":
        cmd_alerts()
    elif args.command == "cost":
        cmd_cost()
    elif args.command == "forecast":
        cmd_forecast()
    else:
        cmd_status()


if __name__ == "__main__":
    main()
