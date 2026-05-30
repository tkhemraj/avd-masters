"""Abstract notifier base."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..models.metrics import HealthStatus


@dataclass
class Alert:
    platform: str
    resource: str
    status: HealthStatus
    message: str
    fired_at: datetime


class BaseNotifier(ABC):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    @abstractmethod
    def notify(self, alert: Alert) -> None:
        """Send a notification for the given alert."""
