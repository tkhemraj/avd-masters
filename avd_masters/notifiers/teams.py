"""Microsoft Teams webhook notifier.

Config keys:
  webhook_url   (required — Incoming Webhook URL from Teams channel)
  mention_all   (default false)
"""

from __future__ import annotations

import logging
from typing import Any

from ..models.metrics import HealthStatus
from .base import Alert, BaseNotifier

logger = logging.getLogger(__name__)

_STATUS_COLORS = {
    HealthStatus.OK: "00CC44",
    HealthStatus.WARNING: "FFA500",
    HealthStatus.CRITICAL: "FF0000",
    HealthStatus.OFFLINE: "808080",
    HealthStatus.UNKNOWN: "808080",
}

_STATUS_ICONS = {
    HealthStatus.OK: "✅",
    HealthStatus.WARNING: "⚠️",
    HealthStatus.CRITICAL: "🔴",
    HealthStatus.OFFLINE: "⬛",
    HealthStatus.UNKNOWN: "❓",
}


class TeamsNotifier(BaseNotifier):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        if not config.get("webhook_url"):
            raise ValueError("teams notifier requires webhook_url in config")

    def notify(self, alert: Alert) -> None:
        try:
            import requests
        except ImportError as exc:
            logger.error("requests not installed — cannot send Teams notification")
            return

        icon = _STATUS_ICONS.get(alert.status, "❓")
        color = _STATUS_COLORS.get(alert.status, "808080")

        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": color,
            "summary": f"AVD Masters Alert — {alert.platform}",
            "sections": [
                {
                    "activityTitle": f"{icon} **{alert.status.value.upper()}** — {alert.platform}",
                    "activitySubtitle": alert.resource,
                    "activityText": alert.message,
                    "facts": [
                        {"name": "Platform", "value": alert.platform},
                        {"name": "Resource", "value": alert.resource},
                        {"name": "Status", "value": alert.status.value.upper()},
                        {"name": "Time", "value": alert.fired_at.strftime("%Y-%m-%d %H:%M:%S UTC")},
                    ],
                }
            ],
        }

        try:
            resp = requests.post(
                self.config["webhook_url"],
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            logger.debug("Teams notification sent for %s/%s", alert.platform, alert.resource)
        except Exception as exc:
            logger.error("Failed to send Teams notification: %s", exc)
