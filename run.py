"""
GROKY 2.0 — The Entry Point

This is what you get when you actually care about the hardware.

Run with:
    python run.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import groky.catalog as catalog


def banner() -> None:
    print(r"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                           GROKY 2.0                                          ║
║                                                                              ║
║           Direct Hardware Truth for Azure Virtual Desktop                    ║
║                    No lies. No bills. Just silicon.                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
""".strip())


def main() -> None:
    banner()

    print("\nCatalog engaged. Modern reality loaded.\n")

    stats = catalog.summarize()
    print(f"  SKUs tracked:        {stats['total_skus']}")
    print(f"  NVIDIA:              {stats['nvidia']}")
    print(f"  AMD:                 {stats['amd']}")
    print(f"  Fractional SKUs:     {stats['fractional_skus']}")
    print(f"  Retiring SKUs:       {stats['retiring_skus']}")
    print()

    print("=== Modern Hardware We Actually Understand ===\n")

    highlights = [
        "Standard_ND96isr_H200_v5",
        "Standard_NC40ads_H100_v5",
        "Standard_ND96isr_H100_v5",
        "Standard_NC32ads_H100_v5",
        "Standard_NV36ads_A10_v5",
        "Standard_NG32ads_V620_v1",
        "Standard_nd96is_mi300x_v5",
    ]

    for sku in highlights:
        spec = catalog.lookup(sku)
        if spec:
            print(f"  {sku:34} → {spec.pretty()}")

    print("\n" + "─" * 70)
    print("High-end dense nodes (≥4 full GPUs):")
    for sku in catalog.get_high_end_nodes():
        print(f"  - {sku}")

    print("\n" + "─" * 70)
    print("This catalog is why GROKY 2.0 is already ahead of the old tools.")
    print("Everything else we build stands on this foundation.")
    print("─" * 70 + "\n")


if __name__ == "__main__":
    main()
