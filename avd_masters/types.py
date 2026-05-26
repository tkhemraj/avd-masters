"""
AVD Masters — Core Types

Shared primitives and type definitions used across the entire system.

This file exists so we don't scatter Literal strings and magic values
all over the codebase. One place. One source of truth.
"""

from __future__ import annotations

from typing import Literal

# =============================================================================
# Fundamental Types
# =============================================================================

Vendor = Literal["nvidia", "amd"]
"""GPU vendor. We are deliberately opinionated — only two that matter for AVD right now."""

HostStatus = Literal["ok", "warning", "critical", "offline", "unknown"]
"""Health state of a session host from AVD Masters' perspective."""

ImbalanceLabel = Literal["balanced", "moderate", "severe"]
"""How bad the load distribution is across the pool."""

Generation = Literal["Blackwell", "Hopper", "Ada", "Ampere", "CDNA3", "Legacy"]
"""GPU architecture generation (for catalog filtering)."""

# =============================================================================
# Useful Type Aliases
# =============================================================================

SkuName = str
HostName = str
Timestamp = str  # ISO format, kept as string at the edge for simplicity
