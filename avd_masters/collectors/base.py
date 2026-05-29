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
            # exc_info only at DEBUG — full stack traces can contain local vars
            # including config dicts that hold credentials.
            self.logger.error("Unexpected error during collection: %s", exc)
            self.logger.debug("Collection traceback:", exc_info=True)
            raise CollectorError(str(exc)) from exc
