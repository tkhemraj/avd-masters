"""
AVD Masters — Main Entry Point

The real CLI for expensive AVD GPU fleets.

Signature commands:
    python run.py midas              # Pure Midas intelligence (brutal truth + quantified gold)
    python run.py touch              # Full one-command experience (recommended)
    python run.py touch --apply-tags # Same as above but actually writes tags

Everything else is supporting firepower.
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
║                                                                              ║
║  Core: midas | touch | touch --apply-tags | discover                         ║
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
    print("Key commands:")
    print("  midas     → Pure intelligence report (gold + brutal truth)")
    print("  touch     → Full experience (discovery + midas + governance + CMMC 2.0 + playbooks)")
    print("  touch --apply-tags → Same as above but actually writes tags (use carefully)")
    print("  discover  | alerts | cost | forecast\n")


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


def cmd_touch(apply_tags: bool = False):
    """
    The ultimate 'Midas Touch' one-command experience.
    Discover → Analyze like Grok → Generate gold tags → Actionable remediation playbooks.
    """
    from avd_masters import discovery, governance, midas, signals

    print("\n" + "═" * 72)
    print("║" + " AVD MASTERS — ONE COMMAND TOUCH ".center(70) + "║")
    print("═" * 72)

    if apply_tags:
        print("\n⚠️  --apply-tags mode enabled. Tags will be written to Azure (use with care).")
    else:
        print("\nRunning in safe dry-run mode (recommended). Use --apply-tags only when you are ready.")

    print("\nThis will attempt to touch your real environment and turn confusion into gold.\n")

    hosts = []
    try:
        print("Phase 1: Discovery + live SKU refresh")
        hosts = discovery.scan_tenant()
        print(f"  Discovered {len(hosts)} GPU hosts.\n")
    except Exception as e:
        print(f"  Live discovery limited ({e}). Using powerful demo mode.\n")

    print("Phase 2: Midas Intelligence + Governance + CMMC 2.0 Alignment")
    try:
        if hosts:
            # Using the more realistic LocalCollector pattern for better signal simulation
            host_names = [getattr(h, 'name', str(h)) for h in hosts[:10]]
            fleet_signals = signals.get_local_collector_fleet(host_names)

            result = midas.perform_midas_touch(hosts, include_demo_data=False, fleet_signals=fleet_signals)
            midas.print_gold_report(result)

            # Governance layer (cross-sub health + policy)
            health = governance.calculate_fleet_health(hosts, monthly_burn=result.total_current_monthly_burn)
            violations = governance.evaluate_policies(hosts)
            governance.print_governance_report(health, violations)

            # CMMC 2.0 Governance Alignment (US-focused framework)
            cmmc_coverage = governance.assess_cmmc_governance(hosts, fleet_health=health)
            governance.print_cmmc_governance_report(cmmc_coverage)
        else:
            result = midas.perform_midas_touch([], include_demo_data=True)
            midas.print_gold_report(result)

            # Still show CMMC value even in demo mode
            cmmc_demo = governance.assess_cmmc_governance([])
            governance.print_cmmc_governance_report(cmmc_demo)
    except Exception as e:
        print(f"  Analysis issue: {e}")
        result = midas.run_midas_demo()

    print("\nPhase 3: Rich Auto-Tagging + Remediation Playbooks")
    try:
        if hosts:
            apply = apply_tags  # from function param
            tagged = discovery.auto_tag_discovered_hosts(hosts, apply_tags=apply)
            mode = "APPLIED" if apply else "dry-run (safe)"
            print(f"  {mode}: Prepared rich avd_masters:* tags for {len(tagged)} hosts.")
            print("  Tags include: cost-per-second, gpu-model, recommendation, last-calculated, etc.")
            if apply:
                print("  ⚠️  Tags were written to Azure. Verify in the portal.")
        else:
            mode = "APPLIED" if apply_tags else "dry-run"
            print(f"  (Demo mode) Would {mode} high-quality avd_masters tags + recommended actions.")

        # Generate and show exportable remediation playbook (text version)
        print("\n  Remediation Playbook (exportable):")
        playbook = midas.generate_remediation_playbook(result, format="text")
        # Print a compact version
        print("  " + "\n  ".join(playbook.splitlines()[:12]))
        print("\n  (Full playbook available via midas.generate_remediation_playbook(result, 'markdown'|'json'))")

        print("\n  Next actions:")
        print("    1. Immediate: Investigate top 3 items from the Midas report.")
        print("    2. This week: Deal with any retiring hardware.")
        print("    3. Ongoing: Get real utilization signals feeding this thing.")
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
    touch_parser = subparsers.add_parser("touch", help="ONE COMMAND: Full discovery + Midas analysis + rich tagging + remediation playbooks")
    touch_parser.add_argument("--apply-tags", action="store_true", help="Actually apply the generated tags (DANGEROUS - dry-run is default)")

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
        cmd_touch(apply_tags=getattr(args, "apply_tags", False))
    else:
        cmd_status()


if __name__ == "__main__":
    main()
