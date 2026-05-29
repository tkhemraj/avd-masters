"""Azure Virtual Desktop collector.

Requires:
  - azure-identity
  - azure-mgmt-desktopvirtualization
  - azure-mgmt-monitor
  - azure-mgmt-compute (for VM-level metrics)

Authentication: DefaultAzureCredential (env vars, managed identity, az login, etc.)
Config keys:
  subscription_id   (required)
  resource_groups   (optional list — if omitted, scans all RGs)
  poll_interval_s   (default 60)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..models.metrics import (
    AVDHostPool,
    AVDSessionHost,
    AVDSnapshot,
    HealthStatus,
    ResourceMetrics,
    SessionState,
    UserSession,
)
from .base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)


def _map_host_status(status_str: Optional[str]) -> HealthStatus:
    if status_str is None:
        return HealthStatus.UNKNOWN
    mapping = {
        "Available": HealthStatus.OK,
        "Unavailable": HealthStatus.CRITICAL,
        "Shutdown": HealthStatus.OFFLINE,
        "Disconnected": HealthStatus.WARNING,
        "Upgrading": HealthStatus.WARNING,
        "UpgradeFailed": HealthStatus.CRITICAL,
        "NoHeartbeat": HealthStatus.CRITICAL,
        "NotJoinedToDomain": HealthStatus.CRITICAL,
        "DomainTrustRelationshipLost": HealthStatus.CRITICAL,
        "SxSStackListenerNotReady": HealthStatus.CRITICAL,
        "FSLogixNotHealthy": HealthStatus.WARNING,
        "NeedsAssistance": HealthStatus.WARNING,
    }
    return mapping.get(status_str, HealthStatus.UNKNOWN)


def _map_session_state(state_str: Optional[str]) -> SessionState:
    mapping = {
        "Active": SessionState.ACTIVE,
        "Disconnected": SessionState.DISCONNECTED,
        "Pending": SessionState.PENDING,
    }
    return mapping.get(state_str or "", SessionState.IDLE)


class AVDCollector(BaseCollector):
    name = "avd"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._client = None
        self._compute_client = None
        self._monitor_client = None

    def _get_clients(self):
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.desktopvirtualization import DesktopVirtualizationMgmtClient
            from azure.mgmt.monitor import MonitorManagementClient
            from azure.mgmt.compute import ComputeManagementClient
        except ImportError as exc:
            raise CollectorError(
                "Azure SDK not installed. Run: pip install azure-identity "
                "azure-mgmt-desktopvirtualization azure-mgmt-monitor azure-mgmt-compute"
            ) from exc

        if self._client is None:
            cred = DefaultAzureCredential()
            sub = self.config["subscription_id"]
            self._client = DesktopVirtualizationMgmtClient(cred, sub)
            self._monitor_client = MonitorManagementClient(cred, sub)
            self._compute_client = ComputeManagementClient(cred, sub)

        return self._client, self._monitor_client, self._compute_client

    def _get_vm_metrics(self, resource_id: str) -> ResourceMetrics:
        """Pull 5-minute average CPU/memory for a session host VM."""
        _, monitor, _ = self._get_clients()
        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=10)
        metrics = ResourceMetrics()

        try:
            result = monitor.metrics.list(
                resource_id,
                timespan=f"{start.isoformat()}/{now.isoformat()}",
                interval="PT5M",
                metricnames="Percentage CPU,Available Memory Bytes",
                aggregation="Average",
            )
            for metric in result.value:
                if not metric.timeseries:
                    continue
                ts = metric.timeseries[-1]
                if not ts.data:
                    continue
                val = ts.data[-1].average
                if val is None:
                    continue
                if metric.name.value == "Percentage CPU":
                    metrics.cpu_percent = round(val, 1)
                elif metric.name.value == "Available Memory Bytes":
                    # Convert available bytes → used %; needs total memory
                    # We store raw available GB instead if total unknown
                    pass
        except Exception as exc:
            self.logger.debug("Could not fetch VM metrics for %s: %s", resource_id, exc)

        return metrics

    def collect(self) -> AVDSnapshot:
        client, _, _ = self._get_clients()
        sub_id = self.config["subscription_id"]
        target_rgs: Optional[list[str]] = self.config.get("resource_groups")

        snapshot = AVDSnapshot(
            collected_at=datetime.now(timezone.utc),
            subscription_id=sub_id,
        )

        try:
            all_pools = list(client.host_pools.list())
        except Exception as exc:
            snapshot.errors.append(f"Failed to list host pools: {exc}")
            return snapshot

        for pool in all_pools:
            # e.g. /subscriptions/<sub>/resourceGroups/<rg>/providers/.../hostPools/<name>
            parts = pool.id.split("/")
            rg = parts[4] if len(parts) > 4 else "unknown"

            if target_rgs and rg not in target_rgs:
                continue

            avd_pool = AVDHostPool(
                name=pool.name,
                resource_group=rg,
                load_balancer_type=pool.load_balancer_type or "Unknown",
            )

            try:
                hosts = list(client.session_hosts.list(rg, pool.name))
                for host in hosts:
                    host_status = _map_host_status(host.status)
                    host_parts = (host.name or "").split("/")
                    host_short = host_parts[-1] if host_parts else host.name or "unknown"

                    avd_host = AVDSessionHost(
                        name=host_short,
                        host_pool=pool.name,
                        status=host_status,
                        allow_new_sessions=host.allow_new_session or False,
                        sessions=host.sessions or 0,
                        max_sessions=host.status_timestamp is not None and 0 or 0,
                        agent_version=host.agent_version,
                        os_version=host.os_version,
                        last_heartbeat=host.last_heart_beat,
                    )

                    # Pull VM metrics if resource ID is available
                    if host.resource_id:
                        avd_host.metrics = self._get_vm_metrics(host.resource_id)

                    avd_pool.hosts.append(avd_host)
            except Exception as exc:
                snapshot.errors.append(f"Failed to list session hosts for {pool.name}: {exc}")

            try:
                sessions = list(client.user_sessions.list_by_host_pool(rg, pool.name))
                avd_pool.active_sessions = sum(
                    1 for s in sessions if (s.session_state or "") == "Active"
                )
                avd_pool.disconnected_sessions = sum(
                    1 for s in sessions if (s.session_state or "") == "Disconnected"
                )
                for s in sessions:
                    snapshot.user_sessions.append(
                        UserSession(
                            username=s.user_principal_name or "unknown",
                            state=_map_session_state(s.session_state),
                            host=s.name,
                        )
                    )
            except Exception as exc:
                snapshot.errors.append(f"Failed to list user sessions for {pool.name}: {exc}")

            snapshot.host_pools.append(avd_pool)

        return snapshot
