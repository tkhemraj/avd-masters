"""Console notifier — prints alerts to stdout via Rich."""

from __future__ import annotations

import logging
from typing import Any

from ..models.metrics import HealthStatus
from .base import Alert, BaseNotifier

logger = logging.getLogger(__name__)


class ConsoleNotifier(BaseNotifier):
    def notify(self, alert: Alert) -> None:
        try:
            from rich.console import Console
            from rich.panel import Panel

            console = Console()
            style_map = {
                HealthStatus.OK: "bold green",
                HealthStatus.WARNING: "bold yellow",
                HealthStatus.CRITICAL: "bold red",
                HealthStatus.OFFLINE: "dim",
                HealthStatus.UNKNOWN: "dim",
            }
            style = style_map.get(alert.status, "white")
            console.print(
                Panel(
                    f"[{style}]{alert.message}[/{style}]",
                    title=f"[{style}]{alert.platform} — {alert.status.value.upper()}[/{style}]",
                    subtitle=alert.resource,
                )
            )
        except ImportError:
            print(
                f"[{alert.fired_at.strftime('%H:%M:%S')}] "
                f"{alert.status.value.upper()} | {alert.platform} | "
                f"{alert.resource} | {alert.message}"
            )
