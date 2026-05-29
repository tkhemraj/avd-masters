"""Shared types for the best-practice analysis engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    CRITICAL = "critical"
    WARNING  = "warning"
    INFO     = "info"
    PASS     = "pass"


class Category(str, Enum):
    AVAILABILITY    = "High Availability"
    CAPACITY        = "Capacity"
    PERFORMANCE     = "Performance"
    CURRENCY        = "Version Currency"
    CONFIGURATION   = "Configuration"
    HYGIENE         = "Operational Hygiene"
    SECURITY        = "Security"
    LICENSING       = "Licensing"


@dataclass
class Finding:
    platform:       str
    severity:       Severity
    category:       Category
    title:          str
    detail:         str
    recommendation: str
    resource:       Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.severity == Severity.PASS
