"""
AVD Masters — Main Entry Point

This is the real command line interface for managing your AVD GPU environment.

The signature experience:
    python run.py midas              # The Midas Touch — Grok inside, magic happens

Other useful commands:
    python run.py                    # Catalog + basic status
    python run.py discover           # Live Azure discovery + dynamic SKU + auto-tagging
    python run.py alerts             # Management + alerting engine
    python run.py cost               # FinOps attribution demo
    python run.py forecast           # Predictive forecasting
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
║                          AVD MASTERS — MIDAS EDITION                           ║
║                                                                              ║
║           Direct Hardware Truth for Azure Virtual Desktop                    ║
║                 Everything it touches turns into gold.                       ║
║                    Grok inside, obviously.                                   ║
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

    print("Run `python run.py midas` — this is the one that pays for itself.\n")
    print("Other: alerts | discover | cost | forecast\n")


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


def cmd_midas():
    """The signature Midas Touch experience — Grok inside, gold on the table."""
    from avd_masters import midas

    print("Running AVD Masters Midas Touch...\n")
    print("This is the part where the tool actually earns its keep.\n")

    try:
        result = midas.run_midas_demo()
        # In a real run with discovery data we would pass hosts here
        # result = midas.perform_midas_touch(hosts=real_hosts)
    except Exception as e:
        print(f"Midas touch failed: {e}")
        print("Falling back to demo mode (still shows the gold).")
        result = midas.run_midas_demo()


def cmd_discover():
    """Real discovery + dynamic SKU refresh + auto-tagging demo."""
    from avd_masters import discovery

    print("Running AVD Masters discovery...\n")
    print("This will:")
    print("  - Scan your Azure tenant for AVD GPU hosts")
    print("  - Discover regions in use")
    print("  - Refresh GPU catalog live from Azure for those regions")
    print("  - Generate auto-tags with current SKU + cost data\n")

    try:
        hosts = discovery.scan_tenant()
        print(f"Discovered {len(hosts)} GPU-capable session hosts.\n")

        if hosts:
            print("Sample discovered hosts:")
            for h in hosts[:5]:
                print(f"  - {h.name} | {h.vm_size} | {h.host_pool}")

            print("\nGenerating auto-tags (dry-run mode)...")
            tagged = discovery.auto_tag_discovered_hosts(hosts, apply_tags=False)
            print(f"Prepared tags for {len(tagged)} hosts.")

    except Exception as e:
        print(f"Discovery failed (likely missing Azure credentials or permissions): {e}")
        print("\nTip: Run `az login` first, or set service principal credentials.")


def main():
    parser = argparse.ArgumentParser(description="AVD Masters - GPU Management for AVD")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Show catalog and basic status")
    subparsers.add_parser("alerts", help="Run full management + alerting demo")
    subparsers.add_parser("cost", help="Run FinOps cost attribution demo")
    subparsers.add_parser("forecast", help="Show predictive forecasting demo")
    subparsers.add_parser("discover", help="Run discovery + dynamic SKU refresh + auto-tagging")
    subparsers.add_parser("midas", help="THE MIDAS TOUCH — Grok intelligence, quantified gold, signature experience")

    args = parser.parse_args()

    if args.command == "alerts":
        cmd_alerts()
    elif args.command == "cost":
        cmd_cost()
    elif args.command == "forecast":
        cmd_forecast()
    elif args.command == "discover":
        cmd_discover()
    elif args.command == "midas":
        cmd_midas()
    else:
        cmd_status()


if __name__ == "__main__":
    main()
