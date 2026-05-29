"""Rich-powered live terminal dashboard for AVD Masters Suite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..models.metrics import (
    AVDSnapshot,
    CitrixSnapshot,
    HealthStatus,
    MasterSnapshot,
    RDSSnapshot,
    SessionState,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

_STATUS_STYLE = {
    HealthStatus.OK: "bold green",
    HealthStatus.WARNING: "bold yellow",
    HealthStatus.CRITICAL: "bold red",
    HealthStatus.OFFLINE: "dim white",
    HealthStatus.UNKNOWN: "dim cyan",
}

_STATUS_ICON = {
    HealthStatus.OK: "●",
    HealthStatus.WARNING: "▲",
    HealthStatus.CRITICAL: "✖",
    HealthStatus.OFFLINE: "○",
    HealthStatus.UNKNOWN: "?",
}

_SESSION_STYLE = {
    SessionState.ACTIVE: "green",
    SessionState.DISCONNECTED: "yellow",
    SessionState.IDLE: "dim",
    SessionState.PENDING: "cyan",
}


def _status_badge(status: HealthStatus) -> Text:
    icon = _STATUS_ICON.get(status, "?")
    style = _STATUS_STYLE.get(status, "white")
    return Text(f"{icon} {status.value.upper()}", style=style)


def _pct_style(value: Optional[float], warn: float = 75, crit: float = 90) -> str:
    if value is None:
        return "dim"
    if value >= crit:
        return "bold red"
    if value >= warn:
        return "bold yellow"
    return "green"


def _fmt_pct(value: Optional[float]) -> str:
    return f"{value:.1f}%" if value is not None else "N/A"


# ── AVD panel ────────────────────────────────────────────────────────────────

def render_avd_panel(snap: Optional[AVDSnapshot]) -> Panel:
    if snap is None:
        return Panel("[dim]Not configured[/dim]", title="[bold cyan]Azure Virtual Desktop[/bold cyan]")

    table = Table(
        show_header=True,
        header_style="bold cyan",
        show_lines=False,
        expand=True,
        box=None,
        padding=(0, 1),
    )
    table.add_column("Host Pool", style="bold", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Hosts", justify="right")
    table.add_column("Sessions", justify="right")
    table.add_column("Avail", justify="right")

    for pool in snap.host_pools:
        badge = _status_badge(pool.status)
        table.add_row(
            pool.name,
            badge,
            str(len(pool.hosts)),
            f"[green]{pool.active_sessions}[/green] / [yellow]{pool.disconnected_sessions}[/yellow]",
            str(pool.available_hosts),
        )

    if snap.host_pools:
        # Session host detail sub-table
        host_table = Table(
            show_header=True,
            header_style="dim cyan",
            show_lines=False,
            expand=True,
            box=None,
            padding=(0, 1),
        )
        host_table.add_column("Session Host", style="dim", no_wrap=True)
        host_table.add_column("Status", justify="center")
        host_table.add_column("Sessions", justify="right")
        host_table.add_column("CPU%", justify="right")
        host_table.add_column("Mem%", justify="right")
        host_table.add_column("New Sess", justify="center")

        for pool in snap.host_pools:
            for host in pool.hosts:
                cpu = host.metrics.cpu_percent
                mem = host.metrics.memory_percent
                host_table.add_row(
                    host.name,
                    _status_badge(host.status),
                    str(host.sessions),
                    Text(_fmt_pct(cpu), style=_pct_style(cpu)),
                    Text(_fmt_pct(mem), style=_pct_style(mem, 85, 95)),
                    "[green]Yes[/green]" if host.allow_new_sessions else "[red]No[/red]",
                )

        from rich.console import Group as RichGroup
        content = RichGroup(table, Text(""), host_table)
    else:
        content = Text("[dim]No host pools found[/dim]")

    errors = ""
    if snap.errors:
        errors = "\n[red]Errors:[/red] " + "; ".join(snap.errors[:3])

    title_status = _status_badge(snap.overall_status)
    title = Text.assemble(
        Text("Azure Virtual Desktop ", style="bold cyan"),
        title_status,
    )

    subtitle = f"[dim]{len(snap.user_sessions)} total sessions | {snap.collected_at.strftime('%H:%M:%S UTC')}[/dim]"
    return Panel(content, title=title, subtitle=subtitle)


# ── RDS panel ────────────────────────────────────────────────────────────────

def render_rds_panel(snap: Optional[RDSSnapshot]) -> Panel:
    if snap is None:
        return Panel("[dim]Not configured[/dim]", title="[bold magenta]Terminal Services[/bold magenta]")

    table = Table(
        show_header=True,
        header_style="bold magenta",
        show_lines=False,
        expand=True,
        box=None,
        padding=(0, 1),
    )
    table.add_column("Host", style="bold", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Active", justify="right")
    table.add_column("Disc.", justify="right")
    table.add_column("CPU%", justify="right")
    table.add_column("Mem%", justify="right")
    table.add_column("Disk%", justify="right")
    table.add_column("Uptime", justify="right")

    for host in snap.session_hosts:
        cpu = host.metrics.cpu_percent
        mem = host.metrics.memory_percent
        disk = host.metrics.disk_percent
        uptime = f"{host.uptime_hours:.0f}h" if host.uptime_hours is not None else "N/A"
        table.add_row(
            host.hostname,
            _status_badge(host.status),
            str(host.active_sessions),
            Text(str(host.disconnected_sessions), style="yellow" if host.disconnected_sessions > 0 else "dim"),
            Text(_fmt_pct(cpu), style=_pct_style(cpu)),
            Text(_fmt_pct(mem), style=_pct_style(mem, 85, 95)),
            Text(_fmt_pct(disk), style=_pct_style(disk, 80, 95)),
            uptime,
        )

    # Broker row
    broker_parts = []
    for b in snap.brokers:
        badge = _status_badge(b.status)
        broker_parts.append(Text.assemble(Text(b.hostname + " "), badge))

    lic_line = ""
    if snap.license_info:
        li = snap.license_info
        lic_style = _STATUS_STYLE.get(li.status, "white")
        lic_line = (
            f"\n[dim]Licensing:[/dim] [{lic_style}]{li.used_cals}/{li.total_cals} CALs "
            f"({li.utilization_percent:.0f}%)[/{lic_style}]"
        )

    from rich.console import Group as RichGroup
    broker_label = Text("Brokers: ", style="dim")
    broker_row = Text.assemble(broker_label, *broker_parts) if broker_parts else Text("[dim]No brokers[/dim]")

    content = RichGroup(table, Text(""), broker_row)

    title = Text.assemble(
        Text("Terminal Services ", style="bold magenta"),
        _status_badge(snap.overall_status),
    )
    subtitle = (
        f"[dim]{snap.total_active_sessions} active, "
        f"{snap.total_disconnected_sessions} disconnected"
        f"{lic_line} | {snap.collected_at.strftime('%H:%M:%S UTC')}[/dim]"
    )
    return Panel(content, title=title, subtitle=subtitle)


# ── Citrix panel ─────────────────────────────────────────────────────────────

def render_citrix_panel(snap: Optional[CitrixSnapshot]) -> Panel:
    if snap is None:
        return Panel("[dim]Not configured[/dim]", title="[bold yellow]Citrix VDI[/bold yellow]")

    table = Table(
        show_header=True,
        header_style="bold yellow",
        show_lines=False,
        expand=True,
        box=None,
        padding=(0, 1),
    )
    table.add_column("Delivery Group", style="bold", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Machines", justify="right")
    table.add_column("Registered", justify="right")
    table.add_column("Active", justify="right")
    table.add_column("Disc.", justify="right")

    for dg in snap.delivery_groups:
        unreg = dg.total_machines - dg.registered_machines
        reg_style = "red" if unreg > 0 else "green"
        table.add_row(
            dg.name + (" [maintenance]" if dg.in_maintenance else ""),
            _status_badge(dg.status),
            str(dg.total_machines),
            Text.assemble(
                Text(str(dg.registered_machines), style=reg_style),
                Text(f"/{dg.total_machines}", style="dim"),
            ),
            Text(str(dg.sessions_active), style="green" if dg.sessions_active > 0 else "dim"),
            Text(str(dg.sessions_disconnected), style="yellow" if dg.sessions_disconnected > 0 else "dim"),
        )

    # Controller row
    ctrl_parts = []
    for c in snap.controllers:
        ctrl_parts.append(Text.assemble(Text(c.name + " "), _status_badge(c.status), Text("  ")))

    from rich.console import Group as RichGroup
    ctrl_row = (
        Text.assemble(Text("Controllers: ", style="dim"), *ctrl_parts)
        if ctrl_parts else Text("[dim]No controllers found[/dim]")
    )
    content = RichGroup(table, Text(""), ctrl_row)

    title = Text.assemble(
        Text(f"Citrix VDI — {snap.site_name} ", style="bold yellow"),
        _status_badge(snap.overall_status),
    )
    subtitle = f"[dim]{snap.total_active_sessions} active sessions | {snap.collected_at.strftime('%H:%M:%S UTC')}[/dim]"
    return Panel(content, title=title, subtitle=subtitle)


# ── Header bar ───────────────────────────────────────────────────────────────

def render_header(snap: MasterSnapshot) -> Panel:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    overall = snap.overall_status
    badge = _status_badge(overall)

    avd_badge = _status_badge(snap.avd.overall_status) if snap.avd else Text("—", style="dim")
    rds_badge = _status_badge(snap.rds.overall_status) if snap.rds else Text("—", style="dim")
    ctx_badge = _status_badge(snap.citrix.overall_status) if snap.citrix else Text("—", style="dim")

    title_text = Text.assemble(
        Text("AVD MASTERS SUITE", style="bold white"),
        Text("  "),
        badge,
        Text(f"  [{now_str}]", style="dim"),
    )

    summary_text = Text.assemble(
        Text("AVD: "), avd_badge,
        Text("  |  RDS: "), rds_badge,
        Text("  |  Citrix: "), ctx_badge,
    )

    from rich.console import Group as RichGroup
    return Panel(
        RichGroup(title_text, summary_text),
        style="bold",
        border_style="bright_blue",
    )


# ── Full layout ──────────────────────────────────────────────────────────────

def render_dashboard(snap: MasterSnapshot) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(render_header(snap), name="header", size=5),
        Layout(name="body"),
    )

    panels = []
    if snap.avd is not None:
        panels.append(render_avd_panel(snap.avd))
    if snap.rds is not None:
        panels.append(render_rds_panel(snap.rds))
    if snap.citrix is not None:
        panels.append(render_citrix_panel(snap.citrix))

    if not panels:
        layout["body"].update(
            Panel("[dim]No platforms configured. Check config.yaml.[/dim]")
        )
    elif len(panels) == 1:
        layout["body"].update(panels[0])
    else:
        layout["body"].update(Columns(panels, equal=True, expand=True))

    return layout


def run_live_dashboard(get_snapshot, refresh_seconds: int = 30) -> None:
    """
    Run the live TUI dashboard.
    get_snapshot: callable() -> MasterSnapshot
    """
    import time

    console = Console()
    console.print("[bold cyan]AVD Masters Suite — starting...[/bold cyan]")

    snap = get_snapshot()

    with Live(render_dashboard(snap), console=console, refresh_per_second=1, screen=True) as live:
        last_refresh = time.monotonic()
        try:
            while True:
                time.sleep(0.5)
                elapsed = time.monotonic() - last_refresh
                if elapsed >= refresh_seconds:
                    try:
                        snap = get_snapshot()
                    except Exception as exc:
                        console.log(f"[red]Collection error: {exc}[/red]")
                    last_refresh = time.monotonic()
                live.update(render_dashboard(snap))
        except KeyboardInterrupt:
            pass
