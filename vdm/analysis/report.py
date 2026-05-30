"""Aggregate findings from all analysers and render a Rich report."""

from __future__ import annotations

from typing import Optional

from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from ..models.metrics import MasterSnapshot
from .base import Category, Finding, Severity

# ── Styles ────────────────────────────────────────────────────────────────────

_SEV_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.WARNING:  "bold yellow",
    Severity.INFO:     "bold cyan",
    Severity.PASS:     "bold green",
}

_SEV_ICON = {
    Severity.CRITICAL: "✖ CRITICAL",
    Severity.WARNING:  "▲ WARNING",
    Severity.INFO:     "● INFO",
    Severity.PASS:     "✔ PASS",
}

_PLATFORM_STYLE = {
    "AVD":    "bold cyan",
    "RDS":    "bold magenta",
    "Citrix": "bold yellow",
}


# ── Runner ────────────────────────────────────────────────────────────────────

def run_analysis(snap: MasterSnapshot, cfg: Optional[dict] = None) -> list[Finding]:
    """Run all applicable analysers against the snapshot."""
    from . import avd as avd_analyser
    from . import rds as rds_analyser
    from . import citrix as citrix_analyser

    findings: list[Finding] = []
    analysis_cfg = cfg or {}

    if snap.avd:
        findings += avd_analyser.analyse(snap.avd, analysis_cfg.get("avd"))
    if snap.rds:
        findings += rds_analyser.analyse(snap.rds, analysis_cfg.get("rds"))
    if snap.citrix:
        findings += citrix_analyser.analyse(snap.citrix, analysis_cfg.get("citrix"))

    return findings


# ── Score ─────────────────────────────────────────────────────────────────────

def score(findings: list[Finding]) -> dict:
    """Return a simple health-score dict per platform and overall."""
    weights = {
        Severity.CRITICAL: 10,
        Severity.WARNING:   3,
        Severity.INFO:      1,
        Severity.PASS:      0,
    }
    platforms = sorted({f.platform for f in findings})
    result = {}
    for platform in platforms:
        pf = [f for f in findings if f.platform == platform]
        deductions = sum(weights[f.severity] for f in pf if not f.passed)
        passes = sum(1 for f in pf if f.passed)
        total = len(pf)
        pct = max(0, 100 - deductions) if total > 0 else 100
        result[platform] = {
            "score": pct,
            "critical": sum(1 for f in pf if f.severity == Severity.CRITICAL),
            "warning":  sum(1 for f in pf if f.severity == Severity.WARNING),
            "info":     sum(1 for f in pf if f.severity == Severity.INFO),
            "pass":     passes,
            "total":    total,
        }

    all_deductions = sum(weights[f.severity] for f in findings if not f.passed)
    result["overall"] = {
        "score": max(0, 100 - all_deductions),
        "critical": sum(1 for f in findings if f.severity == Severity.CRITICAL),
        "warning":  sum(1 for f in findings if f.severity == Severity.WARNING),
        "info":     sum(1 for f in findings if f.severity == Severity.INFO),
        "pass":     sum(1 for f in findings if f.passed),
        "total":    len(findings),
    }
    return result


def _score_style(s: int) -> str:
    if s >= 90:
        return "bold green"
    if s >= 70:
        return "bold yellow"
    return "bold red"


# ── Rich renderers ────────────────────────────────────────────────────────────

def render_summary_table(scores: dict) -> Table:
    table = Table(
        show_header=True,
        header_style="bold white",
        box=None,
        padding=(0, 2),
        expand=False,
    )
    table.add_column("Platform",  style="bold")
    table.add_column("Score",     justify="right")
    table.add_column("Critical",  justify="right")
    table.add_column("Warning",   justify="right")
    table.add_column("Info",      justify="right")
    table.add_column("Pass",      justify="right")
    table.add_column("Checks",    justify="right", style="dim")

    platforms = [p for p in scores if p != "overall"]
    for platform in sorted(platforms):
        s = scores[platform]
        sc = s["score"]
        table.add_row(
            Text(platform, style=_PLATFORM_STYLE.get(platform, "white")),
            Text(str(sc), style=_score_style(sc)),
            Text(str(s["critical"]) if s["critical"] else "—",
                 style="bold red" if s["critical"] else "dim"),
            Text(str(s["warning"]) if s["warning"] else "—",
                 style="bold yellow" if s["warning"] else "dim"),
            Text(str(s["info"]) if s["info"] else "—",
                 style="cyan" if s["info"] else "dim"),
            Text(str(s["pass"]), style="green"),
            str(s["total"]),
        )

    # Overall row
    s = scores["overall"]
    sc = s["score"]
    table.add_section()
    table.add_row(
        Text("Overall", style="bold white"),
        Text(str(sc), style=_score_style(sc)),
        Text(str(s["critical"]) if s["critical"] else "—",
             style="bold red" if s["critical"] else "dim"),
        Text(str(s["warning"]) if s["warning"] else "—",
             style="bold yellow" if s["warning"] else "dim"),
        Text(str(s["info"]) if s["info"] else "—",
             style="cyan" if s["info"] else "dim"),
        Text(str(s["pass"]), style="green"),
        str(s["total"]),
    )
    return table


def render_findings_table(findings: list[Finding],
                          platform: Optional[str] = None,
                          hide_passes: bool = True) -> Table:
    rows = [f for f in findings
            if (platform is None or f.platform == platform)
            and (not hide_passes or not f.passed)]

    table = Table(
        show_header=True,
        header_style="bold white",
        show_lines=True,
        expand=True,
        padding=(0, 1),
    )
    table.add_column("Sev",      width=12, no_wrap=True)
    table.add_column("Category", width=20, no_wrap=True)
    table.add_column("Resource", width=24, no_wrap=True, style="dim")
    table.add_column("Finding",  ratio=2)
    table.add_column("Recommendation", ratio=3)

    for f in rows:
        sev_style = _SEV_STYLE.get(f.severity, "white")
        table.add_row(
            Text(_SEV_ICON[f.severity], style=sev_style),
            f.category.value,
            f.resource or "—",
            Text(f.title, style="bold") + Text(f"\n{f.detail}", style="dim"),
            f.recommendation,
        )

    return table


def render_full_report(findings: list[Finding],
                       hide_passes: bool = True) -> Group:
    """Return a renderable Group for the full report across all platforms."""
    scores = score(findings)
    platforms = sorted({f.platform for f in findings})

    parts = [
        Rule("[bold white]AVD Masters — Best Practice Analysis[/bold white]",
             style="bright_blue"),
        Padding(render_summary_table(scores), (1, 0)),
    ]

    for platform in platforms:
        style = _PLATFORM_STYLE.get(platform, "white")
        platform_findings = [f for f in findings if f.platform == platform]
        actionable = [f for f in platform_findings if not f.passed]

        parts.append(Rule(f"[{style}]{platform}[/{style}]", style="dim"))

        if not actionable:
            parts.append(
                Padding(
                    Text(f"✔  All {len(platform_findings)} checks passed for {platform}.",
                         style="bold green"),
                    (0, 2),
                )
            )
        else:
            parts.append(
                Padding(render_findings_table(platform_findings, hide_passes=hide_passes),
                        (0, 0))
            )

    return Group(*parts)


def print_report(findings: list[Finding],
                 hide_passes: bool = True,
                 console: Optional[Console] = None) -> None:
    c = console or Console()
    c.print(render_full_report(findings, hide_passes=hide_passes))
