"""Config loader — reads config.yaml and validates required fields."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG: dict[str, Any] = {
    "poll_interval_s": 60,
    "log_level": "INFO",
    "notifiers": {"console": {}},
    "avd": None,
    "rds": None,
    "citrix": None,
}


def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("pyyaml not installed. Run: pip install pyyaml") from exc

    config_path = Path(path)
    if not config_path.exists():
        logger.warning("Config file not found at %s — using defaults", config_path)
        return dict(_DEFAULT_CONFIG)

    with open(config_path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    merged = {**_DEFAULT_CONFIG, **raw}

    # Propagate top-level poll_interval_s into each platform block if not set
    for platform in ("avd", "rds", "citrix"):
        if merged.get(platform):
            merged[platform].setdefault("poll_interval_s", merged["poll_interval_s"])

    return merged


def validate_config(config: dict[str, Any]) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors: list[str] = []

    if config.get("avd"):
        if not config["avd"].get("subscription_id"):
            errors.append("avd.subscription_id is required")

    if config.get("rds"):
        if not config["rds"].get("hosts"):
            errors.append("rds.hosts list is required")
        if not config["rds"].get("winrm_username"):
            errors.append("rds.winrm_username is required")
        if not config["rds"].get("winrm_password"):
            errors.append("rds.winrm_password is required")

    if config.get("citrix"):
        citrix = config["citrix"]
        if citrix.get("use_winrm"):
            if not citrix.get("winrm_host"):
                errors.append("citrix.winrm_host is required when use_winrm=true")
            if not citrix.get("winrm_username"):
                errors.append("citrix.winrm_username is required when use_winrm=true")
        else:
            if not citrix.get("director_url"):
                errors.append("citrix.director_url is required")
            if not citrix.get("username"):
                errors.append("citrix.username is required")

        if "teams" in config.get("notifiers", {}):
            if not config["notifiers"]["teams"].get("webhook_url"):
                errors.append("notifiers.teams.webhook_url is required")

    return errors
