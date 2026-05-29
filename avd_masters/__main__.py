"""Entry point: python -m avd_masters [--config path] [--once] [--no-dashboard]"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=getattr(logging, level.upper(), logging.INFO),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="avd-masters",
        description="AVD Masters Suite — unified monitoring for AVD, RDS, and Citrix VDI",
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single collection pass, print JSON output, and exit",
    )
    parser.add_argument(
        "--no-dashboard", action="store_true",
        help="Run headless (alerts only, no TUI)",
    )
    parser.add_argument(
        "--log-level", default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override log level from config",
    )
    args = parser.parse_args(argv)

    from .config import load_config, validate_config

    config = load_config(args.config)
    _setup_logging(args.log_level or config.get("log_level", "INFO"))

    errors = validate_config(config)
    if errors:
        for err in errors:
            print(f"[CONFIG ERROR] {err}", file=sys.stderr)
        return 1

    from .engine import MonitoringEngine

    engine = MonitoringEngine(config)

    if args.once:
        import json, dataclasses

        snap = engine.collect()
        # Simple JSON serialization
        def default(obj):
            if dataclasses.is_dataclass(obj):
                return dataclasses.asdict(obj)
            if hasattr(obj, "value"):
                return obj.value
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)

        print(json.dumps(dataclasses.asdict(snap), default=default, indent=2))
        return 0

    if args.no_dashboard:
        import time
        interval = config.get("poll_interval_s", 60)
        logging.getLogger("avd_masters").info(
            "Running headless, polling every %ss. Ctrl+C to stop.", interval
        )
        try:
            while True:
                engine.collect()
                time.sleep(interval)
        except KeyboardInterrupt:
            pass
        return 0

    # Live TUI dashboard
    from .dashboard.tui import run_live_dashboard

    run_live_dashboard(
        get_snapshot=engine.collect,
        refresh_seconds=config.get("poll_interval_s", 60),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
