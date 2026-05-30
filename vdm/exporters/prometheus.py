"""Prometheus exporter for VirtualDesktopMasters.

Exposes /metrics on a configurable port for Prometheus scraping.

Requires: prometheus_client

Config keys (under prometheus: block):
  port              (default 9090)
  host              (default 0.0.0.0)
  include_sessions  (default false — session-level labels create high cardinality)

Status gauge encoding:
  0 = ok, 1 = warning, 2 = critical, 3 = unknown, 4 = offline
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from ..models.metrics import (
    HealthStatus,
    MasterSnapshot,
)

logger = logging.getLogger(__name__)

_STATUS_VALUE = {
    HealthStatus.OK: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.CRITICAL: 2,
    HealthStatus.UNKNOWN: 3,
    HealthStatus.OFFLINE: 4,
}


def _sv(status: HealthStatus) -> float:
    return float(_STATUS_VALUE.get(status, 3))


class PrometheusExporter:
    def __init__(self, config: dict) -> None:
        self.port = int(config.get("port", 9090))
        self.host = config.get("host", "127.0.0.1")
        self._registry = self._build_registry()
        self._server_thread: Optional[threading.Thread] = None

        if self.host == "0.0.0.0":
            logger.warning(
                "Prometheus /metrics is bound to 0.0.0.0:%s (all interfaces). "
                "The endpoint is unauthenticated — ensure it is protected by a "
                "firewall or reverse proxy in production.",
                self.port,
            )

    # ── Registry / metric definitions ────────────────────────────────────────

    def _build_registry(self):
        try:
            from prometheus_client import CollectorRegistry, Gauge, Counter, Info
        except ImportError as exc:
            raise RuntimeError(
                "prometheus_client not installed. Run: pip install prometheus_client"
            ) from exc

        from prometheus_client import CollectorRegistry, Gauge, Counter

        reg = CollectorRegistry()

        def g(name, doc, labels):
            return Gauge(name, doc, labels, registry=reg)

        def c(name, doc, labels):
            return Counter(name, doc, labels, registry=reg)

        # ── meta ────────────────────────────────────────────────────────────
        self.m_last_scrape = g(
            "vdm_last_collection_timestamp_seconds",
            "Unix timestamp of the last successful collection per platform",
            ["platform"],
        )
        self.m_collection_duration = g(
            "vdm_collection_duration_seconds",
            "Duration of last collection pass in seconds",
            ["platform"],
        )
        self.m_collection_errors = c(
            "vdm_collection_errors_total",
            "Total number of collection errors per platform",
            ["platform"],
        )
        self.m_overall_status = g(
            "vdm_overall_status",
            "Overall health status (0=ok 1=warn 2=crit 3=unknown 4=offline)",
            ["platform"],
        )

        # ── AVD ─────────────────────────────────────────────────────────────
        self.avd_pool_status = g(
            "avd_host_pool_status",
            "Host pool health status",
            ["host_pool", "resource_group"],
        )
        self.avd_pool_active_sessions = g(
            "avd_host_pool_active_sessions",
            "Number of active user sessions in the host pool",
            ["host_pool", "resource_group"],
        )
        self.avd_pool_disconnected_sessions = g(
            "avd_host_pool_disconnected_sessions",
            "Number of disconnected user sessions in the host pool",
            ["host_pool", "resource_group"],
        )
        self.avd_pool_available_hosts = g(
            "avd_host_pool_available_hosts",
            "Number of session hosts accepting new sessions",
            ["host_pool", "resource_group"],
        )
        self.avd_pool_total_hosts = g(
            "avd_host_pool_total_hosts",
            "Total number of session hosts in the host pool",
            ["host_pool", "resource_group"],
        )
        self.avd_host_status = g(
            "avd_session_host_status",
            "Session host health status",
            ["host_pool", "host"],
        )
        self.avd_host_sessions = g(
            "avd_session_host_sessions",
            "Current session count on the session host",
            ["host_pool", "host"],
        )
        self.avd_host_cpu = g(
            "avd_session_host_cpu_percent",
            "Session host CPU utilisation percent",
            ["host_pool", "host"],
        )
        self.avd_host_mem = g(
            "avd_session_host_memory_percent",
            "Session host memory utilisation percent",
            ["host_pool", "host"],
        )
        self.avd_host_allow_new = g(
            "avd_session_host_allow_new_sessions",
            "1 if the host is accepting new sessions, 0 otherwise",
            ["host_pool", "host"],
        )

        # ── RDS ─────────────────────────────────────────────────────────────
        self.rds_host_status = g(
            "rds_session_host_status",
            "RDS session host health status",
            ["farm", "host"],
        )
        self.rds_host_active_sessions = g(
            "rds_session_host_active_sessions",
            "Active sessions on the RDS session host",
            ["farm", "host"],
        )
        self.rds_host_disconnected_sessions = g(
            "rds_session_host_disconnected_sessions",
            "Disconnected sessions on the RDS session host",
            ["farm", "host"],
        )
        self.rds_host_cpu = g(
            "rds_session_host_cpu_percent",
            "RDS session host CPU utilisation percent",
            ["farm", "host"],
        )
        self.rds_host_mem = g(
            "rds_session_host_memory_percent",
            "RDS session host memory utilisation percent",
            ["farm", "host"],
        )
        self.rds_host_disk = g(
            "rds_session_host_disk_percent",
            "RDS session host C: drive utilisation percent",
            ["farm", "host"],
        )
        self.rds_host_uptime = g(
            "rds_session_host_uptime_hours",
            "RDS session host uptime in hours",
            ["farm", "host"],
        )
        self.rds_broker_status = g(
            "rds_broker_status",
            "RD Connection Broker health status",
            ["farm", "broker"],
        )
        self.rds_license_total = g(
            "rds_license_cals_total",
            "Total RDS CALs issued by the licensing server",
            ["farm", "server"],
        )
        self.rds_license_used = g(
            "rds_license_cals_used",
            "RDS CALs currently in use",
            ["farm", "server"],
        )
        self.rds_license_available = g(
            "rds_license_cals_available",
            "RDS CALs available for assignment",
            ["farm", "server"],
        )
        self.rds_license_utilization = g(
            "rds_license_utilization_percent",
            "RDS CAL utilisation as a percentage of total",
            ["farm", "server"],
        )

        # ── Citrix ───────────────────────────────────────────────────────────
        self.ctx_dg_status = g(
            "citrix_delivery_group_status",
            "Citrix delivery group health status",
            ["site", "delivery_group"],
        )
        self.ctx_dg_total_machines = g(
            "citrix_delivery_group_total_machines",
            "Total VDAs in the delivery group",
            ["site", "delivery_group"],
        )
        self.ctx_dg_registered = g(
            "citrix_delivery_group_registered_machines",
            "Registered VDAs in the delivery group",
            ["site", "delivery_group"],
        )
        self.ctx_dg_active_sessions = g(
            "citrix_delivery_group_active_sessions",
            "Active sessions in the delivery group",
            ["site", "delivery_group"],
        )
        self.ctx_dg_disconnected_sessions = g(
            "citrix_delivery_group_disconnected_sessions",
            "Disconnected sessions in the delivery group",
            ["site", "delivery_group"],
        )
        self.ctx_controller_status = g(
            "citrix_controller_status",
            "Citrix Delivery Controller health status",
            ["site", "controller"],
        )

        # ── GPU / vGPU ───────────────────────────────────────────────────────
        self.gpu_util = g(
            "gpu_utilization_percent",
            "Physical GPU SM utilisation percent",
            ["host", "platform", "gpu_index", "gpu_name"],
        )
        self.gpu_mem_util = g(
            "gpu_memory_utilization_percent",
            "Physical GPU VRAM utilisation percent",
            ["host", "platform", "gpu_index", "gpu_name"],
        )
        self.gpu_encoder_util = g(
            "gpu_encoder_utilization_percent",
            "Physical GPU H.264/HEVC encoder utilisation percent",
            ["host", "platform", "gpu_index", "gpu_name"],
        )
        self.gpu_decoder_util = g(
            "gpu_decoder_utilization_percent",
            "Physical GPU decoder utilisation percent",
            ["host", "platform", "gpu_index", "gpu_name"],
        )
        self.gpu_temperature = g(
            "gpu_temperature_celsius",
            "Physical GPU die temperature in Celsius",
            ["host", "platform", "gpu_index", "gpu_name"],
        )
        self.gpu_power_draw = g(
            "gpu_power_draw_watts",
            "Physical GPU power draw in watts",
            ["host", "platform", "gpu_index", "gpu_name"],
        )
        self.gpu_vgpu_count = g(
            "gpu_vgpu_instance_count",
            "Number of active vGPU instances on this physical GPU",
            ["host", "platform", "gpu_index", "gpu_name"],
        )
        self.vgpu_fb_used = g(
            "vgpu_framebuffer_used_mb",
            "Frame buffer used by a vGPU instance in MB",
            ["host", "platform", "gpu_index", "vm_name", "profile", "profile_type"],
        )
        self.vgpu_fb_total = g(
            "vgpu_framebuffer_total_mb",
            "Frame buffer allocated to a vGPU instance in MB",
            ["host", "platform", "gpu_index", "vm_name", "profile", "profile_type"],
        )
        self.vgpu_sm_util = g(
            "vgpu_sm_utilization_percent",
            "vGPU instance shader/compute utilisation percent",
            ["host", "platform", "gpu_index", "vm_name", "profile", "profile_type"],
        )
        self.vgpu_encoder_util = g(
            "vgpu_encoder_utilization_percent",
            "vGPU instance encoder utilisation percent",
            ["host", "platform", "gpu_index", "vm_name", "profile", "profile_type"],
        )
        self.vgpu_decoder_util = g(
            "vgpu_decoder_utilization_percent",
            "vGPU instance decoder utilisation percent",
            ["host", "platform", "gpu_index", "vm_name", "profile", "profile_type"],
        )

        return reg

    # ── Update metrics from a snapshot ───────────────────────────────────────

    def update(self, snap: MasterSnapshot) -> None:
        self.m_overall_status.labels(platform="avd").set(
            _sv(snap.avd.overall_status) if snap.avd else _sv(HealthStatus.UNKNOWN)
        )
        self.m_overall_status.labels(platform="rds").set(
            _sv(snap.rds.overall_status) if snap.rds else _sv(HealthStatus.UNKNOWN)
        )
        self.m_overall_status.labels(platform="citrix").set(
            _sv(snap.citrix.overall_status) if snap.citrix else _sv(HealthStatus.UNKNOWN)
        )

        if snap.avd:
            self._update_avd(snap.avd)
        if snap.rds:
            self._update_rds(snap.rds)
        if snap.citrix:
            self._update_citrix(snap.citrix)
        if snap.gpu:
            self._update_gpu(snap.gpu)

    def _update_avd(self, snap) -> None:
        self.m_last_scrape.labels(platform="avd").set(snap.collected_at.timestamp())
        if snap.errors:
            # increment by number of new errors this pass
            for _ in snap.errors:
                self.m_collection_errors.labels(platform="avd").inc()

        for pool in snap.host_pools:
            lp = {"host_pool": pool.name, "resource_group": pool.resource_group}
            self.avd_pool_status.labels(**lp).set(_sv(pool.status))
            self.avd_pool_active_sessions.labels(**lp).set(pool.active_sessions)
            self.avd_pool_disconnected_sessions.labels(**lp).set(pool.disconnected_sessions)
            self.avd_pool_available_hosts.labels(**lp).set(pool.available_hosts)
            self.avd_pool_total_hosts.labels(**lp).set(len(pool.hosts))

            for host in pool.hosts:
                lh = {"host_pool": pool.name, "host": host.name}
                self.avd_host_status.labels(**lh).set(_sv(host.status))
                self.avd_host_sessions.labels(**lh).set(host.sessions)
                self.avd_host_allow_new.labels(**lh).set(1.0 if host.allow_new_sessions else 0.0)
                if host.metrics.cpu_percent is not None:
                    self.avd_host_cpu.labels(**lh).set(host.metrics.cpu_percent)
                if host.metrics.memory_percent is not None:
                    self.avd_host_mem.labels(**lh).set(host.metrics.memory_percent)

    def _update_rds(self, snap) -> None:
        self.m_last_scrape.labels(platform="rds").set(snap.collected_at.timestamp())
        if snap.errors:
            for _ in snap.errors:
                self.m_collection_errors.labels(platform="rds").inc()

        farm = snap.farm_name
        for host in snap.session_hosts:
            lh = {"farm": farm, "host": host.hostname}
            self.rds_host_status.labels(**lh).set(_sv(host.status))
            self.rds_host_active_sessions.labels(**lh).set(host.active_sessions)
            self.rds_host_disconnected_sessions.labels(**lh).set(host.disconnected_sessions)
            if host.metrics.cpu_percent is not None:
                self.rds_host_cpu.labels(**lh).set(host.metrics.cpu_percent)
            if host.metrics.memory_percent is not None:
                self.rds_host_mem.labels(**lh).set(host.metrics.memory_percent)
            if host.metrics.disk_percent is not None:
                self.rds_host_disk.labels(**lh).set(host.metrics.disk_percent)
            if host.uptime_hours is not None:
                self.rds_host_uptime.labels(**lh).set(host.uptime_hours)

        for broker in snap.brokers:
            self.rds_broker_status.labels(farm=farm, broker=broker.hostname).set(
                _sv(broker.status)
            )

        if snap.license_info:
            li = snap.license_info
            ll = {"farm": farm, "server": li.server}
            self.rds_license_total.labels(**ll).set(li.total_cals)
            self.rds_license_used.labels(**ll).set(li.used_cals)
            self.rds_license_available.labels(**ll).set(li.available_cals)
            self.rds_license_utilization.labels(**ll).set(li.utilization_percent)

    def _update_citrix(self, snap) -> None:
        self.m_last_scrape.labels(platform="citrix").set(snap.collected_at.timestamp())
        if snap.errors:
            for _ in snap.errors:
                self.m_collection_errors.labels(platform="citrix").inc()

        site = snap.site_name
        for dg in snap.delivery_groups:
            ld = {"site": site, "delivery_group": dg.name}
            self.ctx_dg_status.labels(**ld).set(_sv(dg.status))
            self.ctx_dg_total_machines.labels(**ld).set(dg.total_machines)
            self.ctx_dg_registered.labels(**ld).set(dg.registered_machines)
            self.ctx_dg_active_sessions.labels(**ld).set(dg.sessions_active)
            self.ctx_dg_disconnected_sessions.labels(**ld).set(dg.sessions_disconnected)

        for ctrl in snap.controllers:
            self.ctx_controller_status.labels(site=site, controller=ctrl.name).set(
                _sv(ctrl.status)
            )

    def _update_gpu(self, snap) -> None:
        for hostname, host in snap.hosts.items():
            for gpu in host.physical_gpus:
                lp = {
                    "host": hostname,
                    "platform": host.platform,
                    "gpu_index": str(gpu.index),
                    "gpu_name": gpu.name,
                }
                if gpu.gpu_util_pct is not None:
                    self.gpu_util.labels(**lp).set(gpu.gpu_util_pct)
                vram = gpu.vram_util_pct
                if vram is not None:
                    self.gpu_mem_util.labels(**lp).set(vram)
                if gpu.encoder_util_pct is not None:
                    self.gpu_encoder_util.labels(**lp).set(gpu.encoder_util_pct)
                if gpu.decoder_util_pct is not None:
                    self.gpu_decoder_util.labels(**lp).set(gpu.decoder_util_pct)
                if gpu.temperature_c is not None:
                    self.gpu_temperature.labels(**lp).set(gpu.temperature_c)
                if gpu.power_draw_w is not None:
                    self.gpu_power_draw.labels(**lp).set(gpu.power_draw_w)
                self.gpu_vgpu_count.labels(**lp).set(len(gpu.vgpu_instances))

                for inst in gpu.vgpu_instances:
                    li = {
                        "host": hostname,
                        "platform": host.platform,
                        "gpu_index": str(gpu.index),
                        "vm_name": inst.vm_name or inst.instance_id[:16],
                        "profile": inst.profile.raw_name,
                        "profile_type": inst.profile.profile_type,
                    }
                    self.vgpu_fb_used.labels(**li).set(inst.fb_used_mb)
                    self.vgpu_fb_total.labels(**li).set(inst.fb_total_mb)
                    if inst.sm_util_pct is not None:
                        self.vgpu_sm_util.labels(**li).set(inst.sm_util_pct)
                    if inst.encoder_util_pct is not None:
                        self.vgpu_encoder_util.labels(**li).set(inst.encoder_util_pct)
                    if inst.decoder_util_pct is not None:
                        self.vgpu_decoder_util.labels(**li).set(inst.decoder_util_pct)

    # ── HTTP server ───────────────────────────────────────────────────────────

    def start_server(self) -> None:
        """Start the /metrics HTTP server in a background daemon thread."""
        from prometheus_client import start_http_server

        start_http_server(self.port, addr=self.host, registry=self._registry)
        logger.info("Prometheus /metrics listening on %s:%s", self.host, self.port)

    def make_wsgi_app(self):
        """Return a WSGI app for embedding in an existing web server (e.g. gunicorn)."""
        from prometheus_client import make_wsgi_app
        return make_wsgi_app(registry=self._registry)
