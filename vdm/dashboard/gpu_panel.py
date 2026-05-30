"""Rich GPU panel for the TUI dashboard."""

from __future__ import annotations

from typing import Optional

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..models.gpu import GPUSnapshot, HostGPUData, PhysicalGPU, VGPUInstance


def _bar(pct: Optional[float], width: int = 10) -> Text:
    if pct is None:
        return Text("N/A", style="dim")
    filled = max(0, min(width, int(pct / 100 * width)))
    empty = width - filled
    if pct >= 88:
        bar_style = "bold red"
    elif pct >= 70:
        bar_style = "bold yellow"
    else:
        bar_style = "green"
    bar = Text("█" * filled, style=bar_style)
    bar.append("░" * empty, style="dim")
    bar.append(f" {pct:5.1f}%", style=bar_style)
    return bar


def _pct_text(val: Optional[float], warn: float = 70, crit: float = 88) -> Text:
    if val is None:
        return Text("  N/A", style="dim")
    style = "bold red" if val >= crit else ("bold yellow" if val >= warn else "green")
    return Text(f"{val:5.1f}%", style=style)


def _temp_text(val: Optional[float]) -> Text:
    if val is None:
        return Text(" N/A", style="dim")
    style = "bold red" if val >= 90 else ("bold yellow" if val >= 80 else "green")
    return Text(f"{val:.0f}°C", style=style)


def render_gpu_panel(snap: Optional[GPUSnapshot]) -> Panel:
    if snap is None or not snap.hosts:
        return Panel("[dim]GPU monitoring not configured or no GPU hosts found[/dim]",
                     title="[bold white]GPU / vGPU[/bold white]")

    hosts_with_gpu = snap.hosts_with_gpu
    if not hosts_with_gpu:
        return Panel("[dim]No GPU-equipped hosts detected[/dim]",
                     title="[bold white]GPU / vGPU[/bold white]")

    # ── Physical GPU summary table ────────────────────────────────────────────
    pgpu_table = Table(
        show_header=True, header_style="bold white",
        show_lines=False, expand=True, box=None, padding=(0, 1),
    )
    pgpu_table.add_column("Host",     no_wrap=True)
    pgpu_table.add_column("GPU",      no_wrap=True)
    pgpu_table.add_column("Platform", width=7, no_wrap=True)
    pgpu_table.add_column("SM Util",  width=18)
    pgpu_table.add_column("VRAM",     width=18)
    pgpu_table.add_column("Enc",      width=8, justify="right")
    pgpu_table.add_column("Dec",      width=8, justify="right")
    pgpu_table.add_column("Temp",     width=6, justify="right")
    pgpu_table.add_column("Slices",   width=6, justify="right")

    platform_styles = {"avd": "cyan", "rds": "magenta", "citrix": "yellow"}

    for host in sorted(hosts_with_gpu, key=lambda h: h.hostname):
        for gpu in host.physical_gpus:
            vram_pct = gpu.vram_util_pct
            platform_style = platform_styles.get(host.platform.lower(), "white")
            pgpu_table.add_row(
                host.hostname,
                gpu.name[:28],
                Text(host.platform.upper(), style=f"bold {platform_style}"),
                _bar(gpu.gpu_util_pct),
                _bar(vram_pct),
                _pct_text(gpu.encoder_util_pct, 70, 80),
                _pct_text(gpu.decoder_util_pct, 70, 80),
                _temp_text(gpu.temperature_c),
                Text(str(gpu.active_slice_count),
                     style="dim" if gpu.active_slice_count == 0 else "white"),
            )

    # ── vGPU slice detail table ───────────────────────────────────────────────
    all_instances = [
        (host, gpu, inst)
        for host in hosts_with_gpu
        for gpu in host.physical_gpus
        for inst in gpu.vgpu_instances
    ]

    parts: list = [pgpu_table]

    if all_instances:
        parts.append(Text(""))

        vgpu_table = Table(
            show_header=True, header_style="dim white",
            show_lines=False, expand=True, box=None, padding=(0, 1),
        )
        vgpu_table.add_column("VM / Session",   no_wrap=True, width=24)
        vgpu_table.add_column("Profile",        no_wrap=True, width=16)
        vgpu_table.add_column("Type",           no_wrap=True, width=14)
        vgpu_table.add_column("FB Used",        width=18)
        vgpu_table.add_column("SM",             width=8, justify="right")
        vgpu_table.add_column("Enc",            width=8, justify="right")
        vgpu_table.add_column("Dec",            width=8, justify="right")
        vgpu_table.add_column("Status",         width=12, justify="center")

        for host, gpu, inst in sorted(all_instances,
                                       key=lambda x: -(x[2].sm_util_pct or 0)):
            # Status badge
            if inst.is_saturated:
                status = Text("SATURATED", style="bold red")
            elif inst.is_idle:
                status = Text("IDLE", style="dim yellow")
            else:
                status = Text("OK", style="green")

            # Profile type badge
            type_styles = {"Q": "bold yellow", "B": "cyan", "C": "bold magenta", "A": "white"}
            type_style = type_styles.get(inst.profile.profile_type, "white")

            fb_pct_val = inst.fb_util_pct
            vgpu_table.add_row(
                inst.vm_name or inst.instance_id[:20] or "—",
                inst.profile.raw_name[:16],
                Text(inst.profile.type_label, style=type_style),
                _bar(fb_pct_val),
                _pct_text(inst.sm_util_pct),
                _pct_text(inst.encoder_util_pct, 70, 80),
                _pct_text(inst.decoder_util_pct, 70, 80),
                status,
            )

        parts.append(vgpu_table)

    # Summary line
    total_slices = sum(h.vgpu_instance_count for h in hosts_with_gpu)
    total_vram = sum(h.total_vram_mb for h in hosts_with_gpu)
    subtitle = (
        f"[dim]{len(hosts_with_gpu)} GPU host(s) · "
        f"{total_slices} vGPU slice(s) · "
        f"{total_vram // 1024}GB total VRAM | "
        f"{snap.collected_at.strftime('%H:%M:%S UTC')}[/dim]"
    )

    return Panel(
        Group(*parts),
        title="[bold white]GPU / vGPU Slices[/bold white]",
        subtitle=subtitle,
    )
