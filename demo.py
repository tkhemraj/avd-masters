#!/usr/bin/env python3
"""Quick demo: renders the VirtualDesktopMasters dashboard with mock data (no infra needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tests.fixtures import make_master_snapshot
from vdm.dashboard.tui import run_live_dashboard

if __name__ == "__main__":
    print("VirtualDesktopMasters — demo mode (mock data, refreshes every 5s). Ctrl+C to exit.\n")
    run_live_dashboard(get_snapshot=make_master_snapshot, refresh_seconds=5)
