"""Render the AVD Masters dashboard to an HTML file for preview."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tests.fixtures import make_master_snapshot
from avd_masters.dashboard.tui import render_dashboard
from rich.console import Console

snap = make_master_snapshot()
layout = render_dashboard(snap)

# Export to SVG (standalone, no external deps)
c = Console(record=True, width=200, force_terminal=True)
c.print(layout)
svg = c.export_svg(title="AVD Masters Suite — Demo")
Path("avd_masters_demo.svg").write_text(svg)
print("Saved: avd_masters_demo.svg")

# Also export to HTML
html = c.export_html(inline_styles=True)
Path("avd_masters_demo.html").write_text(html)
print("Saved: avd_masters_demo.html")
