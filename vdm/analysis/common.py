"""Shared helpers for the best-practice analysers.

Keeps version comparison, EOL OS detection, and list formatting in one place so
the AVD / RDS / Citrix analysers stay consistent and DRY.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional


# ── Version handling ─────────────────────────────────────────────────────────

def version_key(v: str) -> tuple[int, ...]:
    """Turn a dotted version string into a comparable tuple of ints.

    "1.0.7982.1500" -> (1, 0, 7982, 1500). Non-numeric chunks are dropped so
    that "7.2402.0.0" and "1.0.10000" compare numerically rather than
    lexically (the naive max() over strings ranks "1.0.7982" above
    "1.0.10000", which is wrong).
    """
    parts = re.findall(r"\d+", v or "")
    return tuple(int(p) for p in parts) if parts else (0,)


def latest_version(versions: Iterable[str]) -> Optional[str]:
    """Return the highest version string by numeric ordering, or None."""
    vs = [v for v in versions if v]
    if not vs:
        return None
    return max(vs, key=version_key)


# ── Operating-system end-of-life ─────────────────────────────────────────────
#
# Conservative, low-false-positive detection. We only flag builds/strings that
# are unambiguously out of Microsoft support. The 10.0.x line (Win10/11 and
# Server 2016/2019/2022 all share the 10.0 major) is intentionally NOT matched
# by build number alone — too ambiguous — so we match those by product text
# where the platform gives it to us (e.g. Citrix OSType).

# (regex, product name, end-of-support date)  — ordered most-specific first
_EOL_RULES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\b6\.0\.\d+"),            "Windows Vista / Server 2008",      "2020-01-14"),
    (re.compile(r"\b6\.1\.\d+"),            "Windows 7 / Server 2008 R2",       "2020-01-14"),
    (re.compile(r"\b6\.2\.\d+"),            "Windows 8 / Server 2012",          "2023-10-10"),
    (re.compile(r"\b6\.3\.\d+"),            "Windows 8.1 / Server 2012 R2",     "2023-10-10"),
    (re.compile(r"server\s*2008",  re.I),   "Windows Server 2008/2008 R2",      "2020-01-14"),
    (re.compile(r"server\s*2012",  re.I),   "Windows Server 2012/2012 R2",      "2023-10-10"),
    (re.compile(r"windows\s*7\b",  re.I),   "Windows 7",                        "2020-01-14"),
    (re.compile(r"windows\s*8(\.1)?\b", re.I), "Windows 8 / 8.1",               "2023-01-10"),
]


def os_eol(os_string: Optional[str]) -> Optional[tuple[str, str]]:
    """If the OS string denotes an out-of-support OS, return (name, eol_date).

    Returns None when the OS is current or cannot be classified confidently.
    """
    if not os_string:
        return None
    for pattern, name, eol_date in _EOL_RULES:
        if pattern.search(os_string):
            return name, eol_date
    return None


# ── Formatting ───────────────────────────────────────────────────────────────

def summarize_names(names: Iterable[str], limit: int = 5) -> str:
    """Join names for a finding detail, truncating with an ellipsis past `limit`."""
    names = list(names)
    shown = ", ".join(names[:limit])
    return shown + ("…" if len(names) > limit else "")
