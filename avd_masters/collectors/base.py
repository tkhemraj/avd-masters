"""Abstract base class for all platform collectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class CollectorError(Exception):
    pass


class BaseCollector(ABC):
    name: str = "base"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.logger = logging.getLogger(f"avd_masters.collector.{self.name}")

    @abstractmethod
    def collect(self) -> Any:
        """Run a full collection pass and return a platform snapshot."""

    def safe_collect(self) -> Any:
        try:
            return self.collect()
        except CollectorError:
            raise
        except Exception as exc:
            self.logger.error("Unexpected error during collection: %s", exc, exc_info=True)
            raise CollectorError(str(exc)) from exc
