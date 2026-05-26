#!/usr/bin/env python3
"""
AVD Masters — FinOps Demo

This script demonstrates the cost attribution and auto-tagging capabilities.

Run it with:
    python examples/finops_demo.py

It shows:
- Cost per second / hour calculations for real SKUs
- Auto-generated Azure tags ready for tagging
- A sample showback-style report
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

# Import from the avd_masters package
import sys
from pathlib import Path

# Allow running from the project root without installation
sys.path.insert(0, str(Path(__file__).parent.parent))

from avd_masters import catalog, cost


def main():
    print("╔" + "═" * 70 + "╗")
    print("║" + " AVD Masters — FinOps & Cost Attribution Demo".center(70) + "║")
    print("╚" + "═" * 70 + "╝")
    print()

    # Sample hosts with realistic usage
    sample_hosts = [
        {
            "name": "avd-gpu-prod-01",
            "sku": "Standard_NC32ads_H100_v5",
            "gpu_seconds": 86400 * 2.3,  # ~2.3 days of GPU time
            "region": "eastus",
        },
        {
            "name": "avd-gpu-fract-07",
            "sku": "Standard_NC4ads_H100_v5",
            "gpu_seconds": 86400 * 18.5,  # Heavily used fractional
            "region": "eastus",
        },
        {
            "name": "avd-amd-gaming-03",
            "sku": "Standard_NG32ads_V620_v1",
            "gpu_seconds": 86400 * 7.1,
            "region": "westeurope",
        },
    ]

    print("=== 1. Individual Host Cost Analysis ===\n")

    all_tags = []
    report_rows = []

    for host in sample_hosts:
        spec = catalog.lookup(host["sku"])
        if not spec:
            print(f"  [WARN] Unknown SKU: {host['sku']}")
            continue

        summary = cost.get_cost_summary_for_host(
            host_name=host["name"],
            spec=spec,
            sku=host["sku"],
            total_gpu_seconds=host["gpu_seconds"],
            region=host["region"],
        )

        tags = cost.generate_cost_tags(
            host_name=host["name"],
            spec=spec,
            sku=host["sku"],
            gpu_seconds=host["gpu_seconds"],
            region=host["region"],
        )

        all_tags.append({"host": host["name"], "tags": tags})

        print(f"Host: {host['name']}")
        print(f"  SKU:           {host['sku']}")
        print(f"  GPU:           {spec.model} × {spec.gpu_count}")
        print(f"  GPU-Seconds:   {host['gpu_seconds']:,.0f}")
        print(f"  Cost / Second: ${summary['cost_per_second']:.8f}")
        print(f"  Cost / Hour:   ${summary['cost_per_hour']:.4f}")
        print(f"  Est. Total:    ${summary['estimated_cost_usd']:.2f}")
        print()

        report_rows.append({
            "host": host["name"],
            "model": spec.model,
            "cost": summary['estimated_cost_usd'],
        })

    # === Sample Azure Tags ===
    print("=== 2. Auto-Generated Azure Tags (ready to apply) ===\n")

    for item in all_tags:
        print(f"Host: {item['host']}")
        print(json.dumps(item["tags"], indent=2))
        print()

    # === Fake Showback Report ===
    print("=== 3. Sample Showback Report ===\n")

    total_cost = sum(r["cost"] or 0 for r in report_rows)

    print("AVD Masters FinOps Showback Report")
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
    print(f"{'Host':<25} {'GPU Model':<12} {'Est. Cost (USD)':>15}")
    print("-" * 55)

    for row in report_rows:
        cost_str = f"${row['cost']:.2f}" if row['cost'] else "N/A"
        print(f"{row['host']:<25} {row['model']:<12} {cost_str:>15}")

    print("-" * 55)
    print(f"{'TOTAL':<25} {'':<12} ${total_cost:>13.2f}")
    print()

    print("These tags and numbers can be:")
    print("  • Applied via Azure SDK / Azure Policy")
    print("  • Exported to Cost Management")
    print("  • Used for internal chargeback to business units")
    print()

    # === Dynamic SKU + Auto Tagging demo ===
    print("=== 4. Dynamic SKU Lookup + Auto-Tagging (on load) ===\n")
    print("AVD Masters can now:")
    print("  - Discover current GPU SKUs from Azure for every region you have resources in")
    print("  - Auto-apply rich tags with live cost data on every poll/load")
    print("  - Stay fresh instead of relying on a static 2025-era list\n")

    print("Example auto-tag call with live SKU data (stubbed for demo):")
    print("  tags = avd_masters.cost.auto_tag_host_with_live_sku(")
    print("      host_name='avd-h100-01',")
    print("      sku='Standard_NC32ads_H100_v5',")
    print("      gpu_seconds=180000,")
    print("      region='eastus',")
    print("      compute_client=your_azure_compute_client")
    print("  )\n")

    print("╔" + "═" * 70 + "╗")
    print("║" + " End of FinOps Demo — Real cost visibility + dynamic SKUs + auto-tagging ".center(70) + "║")
    print("╚" + "═" * 70 + "╝")


if __name__ == "__main__":
    main()
