"""Monitoring engine — orchestrates collectors, evaluates alerts, fires notifiers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .collectors.base import BaseCollector, CollectorError
from .models.metrics import (
    AVDSnapshot,
    CitrixSnapshot,
    HealthStatus,
    MasterSnapshot,
    RDSSnapshot,
)
from .notifiers.base import Alert, BaseNotifier

logger = logging.getLogger(__name__)

# Alert thresholds — override via config
_DEFAULT_THRESHOLDS = {
    "avd_host_cpu_warn": 75.0,
    "avd_host_cpu_crit": 90.0,
    "avd_host_mem_warn": 85.0,
    "avd_host_mem_crit": 95.0,
    "rds_host_cpu_warn": 75.0,
    "rds_host_cpu_crit": 90.0,
    "rds_host_mem_warn": 85.0,
    "rds_host_mem_crit": 95.0,
    "rds_license_warn": 80.0,
    "rds_license_crit": 95.0,
    "citrix_unregistered_warn": 1,    # any unregistered VDA = warning
    "citrix_unregistered_crit": 3,    # 3+ unregistered VDAs = critical
}


def _build_notifiers(notifier_config: dict[str, Any]) -> list[BaseNotifier]:
    from .notifiers.console import ConsoleNotifier
    from .notifiers.teams import TeamsNotifier

    notifiers: list[BaseNotifier] = []
    if "console" in notifier_config:
        notifiers.append(ConsoleNotifier(notifier_config["console"] or {}))
    if "teams" in notifier_config:
        try:
            notifiers.append(TeamsNotifier(notifier_config["teams"] or {}))
        except ValueError as exc:
            logger.warning("Teams notifier disabled: %s", exc)
    return notifiers


class MonitoringEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.thresholds = {**_DEFAULT_THRESHOLDS, **config.get("thresholds", {})}
        self.notifiers = _build_notifiers(config.get("notifiers", {"console": {}}))

        self._avd_collector: Optional[BaseCollector] = None
        self._rds_collector: Optional[BaseCollector] = None
        self._citrix_collector: Optional[BaseCollector] = None
        self._prometheus: Optional[Any] = None

        self._last_alert_state: dict[str, HealthStatus] = {}

        self._setup_collectors()
        self._setup_prometheus()

    def _setup_prometheus(self) -> None:
        prom_cfg = self.config.get("prometheus")
        if not prom_cfg:
            return
        try:
            from .exporters.prometheus import PrometheusExporter
            self._prometheus = PrometheusExporter(prom_cfg)
            self._prometheus.start_server()
        except Exception as exc:
            logger.error("Prometheus exporter failed to start: %s", exc)

    def _setup_collectors(self) -> None:
        if self.config.get("avd"):
            from .collectors.avd import AVDCollector
            self._avd_collector = AVDCollector(self.config["avd"])
            logger.info("AVD collector configured")

        if self.config.get("rds"):
            from .collectors.rds import RDSCollector
            self._rds_collector = RDSCollector(self.config["rds"])
            logger.info("RDS collector configured")

        if self.config.get("citrix"):
            from .collectors.citrix import make_citrix_collector
            self._citrix_collector = make_citrix_collector(self.config["citrix"])
            logger.info("Citrix collector configured")

    def collect(self) -> MasterSnapshot:
        snap = MasterSnapshot(collected_at=datetime.now(timezone.utc))

        if self._avd_collector:
            try:
                snap.avd = self._avd_collector.safe_collect()
            except CollectorError as exc:
                logger.error("AVD collection failed: %s", exc)
                snap.avd = AVDSnapshot(
                    collected_at=datetime.now(timezone.utc),
                    subscription_id=self.config["avd"].get("subscription_id", "unknown"),
                    errors=[str(exc)],
                )

        if self._rds_collector:
            try:
                snap.rds = self._rds_collector.safe_collect()
            except CollectorError as exc:
                logger.error("RDS collection failed: %s", exc)
                snap.rds = RDSSnapshot(
                    collected_at=datetime.now(timezone.utc),
                    farm_name=self.config["rds"].get("farm_name", "RDS Farm"),
                    errors=[str(exc)],
                )

        if self._citrix_collector:
            try:
                snap.citrix = self._citrix_collector.safe_collect()
            except CollectorError as exc:
                logger.error("Citrix collection failed: %s", exc)
                snap.citrix = CitrixSnapshot(
                    collected_at=datetime.now(timezone.utc),
                    site_name=self.config["citrix"].get("site_name", "Citrix Site"),
                    errors=[str(exc)],
                )

        self._evaluate_alerts(snap)

        if self._prometheus:
            try:
                self._prometheus.update(snap)
            except Exception as exc:
                logger.error("Prometheus metrics update failed: %s", exc)

        return snap

    def _fire_alert(self, key: str, platform: str, resource: str, status: HealthStatus, message: str) -> None:
        previous = self._last_alert_state.get(key)
        self._last_alert_state[key] = status

        # Only notify on state transitions or new alerts
        if previous == status:
            return

        alert = Alert(
            platform=platform,
            resource=resource,
            status=status,
            message=message,
            fired_at=datetime.now(timezone.utc),
        )
        for notifier in self.notifiers:
            try:
                notifier.notify(alert)
            except Exception as exc:
                logger.error("Notifier %s failed: %s", type(notifier).__name__, exc)

    def _evaluate_alerts(self, snap: MasterSnapshot) -> None:
        if snap.avd:
            self._eval_avd_alerts(snap.avd)
        if snap.rds:
            self._eval_rds_alerts(snap.rds)
        if snap.citrix:
            self._eval_citrix_alerts(snap.citrix)

    def _eval_avd_alerts(self, snap: AVDSnapshot) -> None:
        for pool in snap.host_pools:
            key = f"avd.pool.{pool.name}"
            if pool.status != HealthStatus.OK:
                self._fire_alert(
                    key, "AVD", pool.name,
                    pool.status,
                    f"Host pool '{pool.name}' is {pool.status.value}: "
                    f"{pool.available_hosts}/{len(pool.hosts)} hosts available",
                )
            else:
                self._fire_alert(key, "AVD", pool.name, HealthStatus.OK,
                                 f"Host pool '{pool.name}' recovered")

            for host in pool.hosts:
                hkey = f"avd.host.{host.name}"
                if host.status in (HealthStatus.CRITICAL, HealthStatus.OFFLINE):
                    self._fire_alert(
                        hkey, "AVD", host.name,
                        host.status,
                        f"Session host '{host.name}' status: {host.status.value}",
                    )
                elif host.metrics.cpu_percent is not None:
                    cpu = host.metrics.cpu_percent
                    crit = self.thresholds["avd_host_cpu_crit"]
                    warn = self.thresholds["avd_host_cpu_warn"]
                    if cpu >= crit:
                        self._fire_alert(hkey, "AVD", host.name, HealthStatus.CRITICAL,
                                         f"CPU at {cpu:.1f}% (threshold {crit}%)")
                    elif cpu >= warn:
                        self._fire_alert(hkey, "AVD", host.name, HealthStatus.WARNING,
                                         f"CPU at {cpu:.1f}% (threshold {warn}%)")
                    else:
                        self._fire_alert(hkey, "AVD", host.name, HealthStatus.OK, "OK")

    def _eval_rds_alerts(self, snap: RDSSnapshot) -> None:
        for host in snap.session_hosts:
            hkey = f"rds.host.{host.hostname}"
            if host.status == HealthStatus.OFFLINE:
                self._fire_alert(hkey, "RDS", host.hostname, HealthStatus.CRITICAL,
                                 f"Session host '{host.hostname}' is unreachable")
            else:
                cpu = host.metrics.cpu_percent
                mem = host.metrics.memory_percent
                disk = host.metrics.disk_percent
                worst = HealthStatus.OK
                msg_parts = []
                for val, warn_t, crit_t, label in (
                    (cpu, self.thresholds["rds_host_cpu_warn"], self.thresholds["rds_host_cpu_crit"], "CPU"),
                    (mem, self.thresholds["rds_host_mem_warn"], self.thresholds["rds_host_mem_crit"], "Mem"),
                    (disk, 80.0, 95.0, "Disk"),
                ):
                    if val is None:
                        continue
                    if val >= crit_t:
                        worst = HealthStatus.CRITICAL
                        msg_parts.append(f"{label} {val:.1f}%")
                    elif val >= warn_t:
                        if worst != HealthStatus.CRITICAL:
                            worst = HealthStatus.WARNING
                        msg_parts.append(f"{label} {val:.1f}%")

                msg = f"{host.hostname}: {', '.join(msg_parts)}" if msg_parts else "OK"
                self._fire_alert(hkey, "RDS", host.hostname, worst, msg)

        if snap.license_info:
            li = snap.license_info
            lkey = f"rds.license.{li.server}"
            self._fire_alert(
                lkey, "RDS", f"Licensing ({li.server})",
                li.status,
                f"CAL usage: {li.used_cals}/{li.total_cals} ({li.utilization_percent:.0f}%)",
            )

    def _eval_citrix_alerts(self, snap: CitrixSnapshot) -> None:
        for dg in snap.delivery_groups:
            key = f"citrix.dg.{dg.name}"
            unreg = dg.total_machines - dg.registered_machines
            crit_t = self.thresholds["citrix_unregistered_crit"]
            warn_t = self.thresholds["citrix_unregistered_warn"]
            if unreg >= crit_t:
                self._fire_alert(key, "Citrix", dg.name, HealthStatus.CRITICAL,
                                 f"{unreg} unregistered VDAs in delivery group '{dg.name}'")
            elif unreg >= warn_t:
                self._fire_alert(key, "Citrix", dg.name, HealthStatus.WARNING,
                                 f"{unreg} unregistered VDA(s) in delivery group '{dg.name}'")
            else:
                self._fire_alert(key, "Citrix", dg.name, HealthStatus.OK,
                                 f"Delivery group '{dg.name}' OK")

        for ctrl in snap.controllers:
            ckey = f"citrix.ctrl.{ctrl.name}"
            if ctrl.status != HealthStatus.OK:
                self._fire_alert(ckey, "Citrix", ctrl.name, ctrl.status,
                                 f"Controller '{ctrl.name}' state: {ctrl.state}")
