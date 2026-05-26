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

    print("Run `python run.py midas` or `python run.py touch` — these are the ones that pay for themselves.\n")
    print("Commands: midas | touch | discover | alerts | cost | forecast\n")


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
    from avd_masters import discovery, midas

    print("Running AVD Masters Midas Touch...\n")
    print("Attempting to touch your actual environment for real gold...\n")

    hosts = []
    try:
        print("  → Running live discovery (this may take a moment)...")
        hosts = discovery.scan_tenant()
        print(f"  → Discovered {len(hosts)} hosts.\n")
    except Exception as e:
        print(f"  → Live discovery not available in this environment ({e}).")
        print("  → Using rich demo data with the same analysis engine.\n")

    try:
        if hosts:
            result = midas.perform_midas_touch(hosts=hosts, include_demo_data=False)
            midas.print_gold_report(result)
        else:
            result = midas.run_midas_demo()
    except Exception as e:
        print(f"Midas analysis hit an issue: {e}")
        print("Falling back to the strongest demo report we have...")
        result = midas.run_midas_demo()


def cmd_touch():
    """
    The ultimate 'Midas Touch' one-command experience.
    Discover → Analyze like Grok → Generate gold tags → Actionable remediation playbooks.
    """
    from avd_masters import discovery, governance, midas, signals

    print("\n" + "═" * 72)
    print("║" + " AVD MASTERS — ONE COMMAND TOUCH ".center(70) + "║")
    print("═" * 72)
    print("\nThis will attempt to touch your real environment and turn confusion into gold.\n")

    hosts = []
    try:
        print("Phase 1: Discovery + live SKU refresh")
        hosts = discovery.scan_tenant()
        print(f"  Discovered {len(hosts)} GPU hosts.\n")
    except Exception as e:
        print(f"  Live discovery limited ({e}). Using powerful demo mode.\n")

    print("Phase 2: Midas Intelligence Analysis + Governance Overlay")
    try:
        if hosts:
            demo_signals = signals.get_simulated_fleet([getattr(h, 'name', str(h)) for h in hosts[:8]])
            result = midas.perform_midas_touch(hosts, include_demo_data=False, fleet_signals=demo_signals)
            midas.print_gold_report(result)

            # Governance layer (cross-sub health + policy)
            health = governance.calculate_fleet_health(hosts, monthly_burn=result.total_current_monthly_burn)
            violations = governance.evaluate_policies(hosts)
            governance.print_governance_report(health, violations)
        else:
            result = midas.perform_midas_touch([], include_demo_data=True)
            midas.print_gold_report(result)
    except Exception as e:
        print(f"  Analysis issue: {e}")
        result = midas.run_midas_demo()

    print("\nPhase 3: Rich Auto-Tagging + Remediation Playbooks")
    try:
        if hosts:
            tagged = discovery.auto_tag_discovered_hosts(hosts, apply_tags=False)
            print(f"  Prepared rich avd_masters:* tags for {len(tagged)} hosts (dry-run).")
            print("  Tags include: cost-per-second, gpu-model, recommendation, last-calculated, etc.")
        else:
            print("  (Demo mode) Would generate high-quality Azure tags + recommended actions for every host above.")

        # Generate simple but powerful remediation playbooks
        print("\n  Remediation Playbooks (prioritized):")
        print("    1. Immediate: Investigate top 3 idle/oversized hosts from the Midas report above.")
        print("    2. This week: Migrate any retiring hardware (Tesla M60 etc.).")
        print("    3. This month: Run packing analysis on fractional H100/MI300X hosts.")
        print("    4. Ongoing: Enable the signals collector so future `touch` runs are scary accurate.")
    except Exception as e:
        print(f"  Tagging prep: {e}")

    print("\n" + "═" * 72)
    print("  Next level: Real utilization signals + --apply-tags for one-command safe remediation.")
    print("  The gold is real. Go touch it.")
    print("═" * 72 + "\n")


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
    subparsers.add_parser("touch", help="ONE COMMAND: Full discovery + Midas analysis + rich tagging + remediation playbooks")

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
    elif args.command == "touch":
        cmd_touch()
    else:
        cmd_status()


if __name__ == "__main__":
    main()
