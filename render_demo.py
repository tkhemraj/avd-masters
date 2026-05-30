"""Render the AVD Masters dashboard to an HTML file for preview."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tests.fixtures import make_master_snapshot
from vdm.dashboard.tui import render_dashboard
from rich.console import Console

snap = make_master_snapshot()
layout = render_dashboard(snap)

# Export to SVG (standalone, no external deps)
c = Console(record=True, width=200, force_terminal=True)
c.print(layout)
svg = c.export_svg(title="AVD Masters Suite — Demo")
Path("vdm_demo.svg").write_text(svg)
print("Saved: vdm_demo.svg")

# Also export to HTML
html = c.export_html(inline_styles=True)
Path("vdm_demo.html").write_text(html)
print("Saved: vdm_demo.html")
