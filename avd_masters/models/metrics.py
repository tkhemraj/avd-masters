"""Shared data models for all platform collectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class HealthStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    OFFLINE = "offline"


class SessionState(str, Enum):
    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    PENDING = "pending"


@dataclass
class ResourceMetrics:
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None


@dataclass
class UserSession:
    username: str
    state: SessionState
    session_id: Optional[str] = None
    host: Optional[str] = None
    logon_time: Optional[datetime] = None
    idle_minutes: Optional[int] = None
    client_ip: Optional[str] = None


# ── Azure Virtual Desktop ────────────────────────────────────────────────────

@dataclass
class AVDSessionHost:
    name: str
    host_pool: str
    status: HealthStatus
    allow_new_sessions: bool
    sessions: int
    max_sessions: int
    agent_version: Optional[str] = None
    os_version: Optional[str] = None
    metrics: ResourceMetrics = field(default_factory=ResourceMetrics)
    last_heartbeat: Optional[datetime] = None


@dataclass
class AVDHostPool:
    name: str
    resource_group: str
    load_balancer_type: str
    hosts: list[AVDSessionHost] = field(default_factory=list)
    active_sessions: int = 0
    disconnected_sessions: int = 0

    @property
    def status(self) -> HealthStatus:
        if not self.hosts:
            return HealthStatus.UNKNOWN
        critical = sum(1 for h in self.hosts if h.status == HealthStatus.CRITICAL)
        if critical == len(self.hosts):
            return HealthStatus.CRITICAL
        if critical > 0:
            return HealthStatus.WARNING
        return HealthStatus.OK

    @property
    def available_hosts(self) -> int:
        return sum(1 for h in self.hosts if h.status == HealthStatus.OK and h.allow_new_sessions)


@dataclass
class AVDSnapshot:
    collected_at: datetime
    subscription_id: str
    host_pools: list[AVDHostPool] = field(default_factory=list)
    user_sessions: list[UserSession] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def overall_status(self) -> HealthStatus:
        if self.errors and not self.host_pools:
            return HealthStatus.UNKNOWN
        statuses = [p.status for p in self.host_pools]
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        if HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        return HealthStatus.OK


# ── On-Premises Terminal Services (RDS) ─────────────────────────────────────

@dataclass
class RDSHost:
    hostname: str
    status: HealthStatus
    active_sessions: int = 0
    disconnected_sessions: int = 0
    max_sessions: int = 0
    metrics: ResourceMetrics = field(default_factory=ResourceMetrics)
    os_version: Optional[str] = None
    uptime_hours: Optional[float] = None


@dataclass
class RDSLicenseInfo:
    server: str
    total_cals: int = 0
    used_cals: int = 0
    available_cals: int = 0

    @property
    def utilization_percent(self) -> float:
        if self.total_cals == 0:
            return 0.0
        return (self.used_cals / self.total_cals) * 100

    @property
    def status(self) -> HealthStatus:
        pct = self.utilization_percent
        if pct >= 95:
            return HealthStatus.CRITICAL
        if pct >= 80:
            return HealthStatus.WARNING
        return HealthStatus.OK


@dataclass
class RDSBroker:
    hostname: str
    status: HealthStatus
    is_active: bool = True
    connection_broker_role: Optional[str] = None


@dataclass
class RDSSnapshot:
    collected_at: datetime
    farm_name: str
    session_hosts: list[RDSHost] = field(default_factory=list)
    brokers: list[RDSBroker] = field(default_factory=list)
    license_info: Optional[RDSLicenseInfo] = None
    user_sessions: list[UserSession] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_active_sessions(self) -> int:
        return sum(h.active_sessions for h in self.session_hosts)

    @property
    def total_disconnected_sessions(self) -> int:
        return sum(h.disconnected_sessions for h in self.session_hosts)

    @property
    def overall_status(self) -> HealthStatus:
        if self.errors and not self.session_hosts:
            return HealthStatus.UNKNOWN
        host_statuses = [h.status for h in self.session_hosts]
        broker_statuses = [b.status for b in self.brokers]
        all_statuses = host_statuses + broker_statuses
        if not all_statuses:
            return HealthStatus.UNKNOWN
        if HealthStatus.CRITICAL in all_statuses:
            return HealthStatus.CRITICAL
        if HealthStatus.WARNING in all_statuses:
            return HealthStatus.WARNING
        return HealthStatus.OK


# ── Citrix VDI ───────────────────────────────────────────────────────────────

@dataclass
class CitrixMachine:
    name: str
    delivery_group: str
    catalog: str
    registration_state: str  # Registered, Unregistered, Unknown
    power_state: str          # On, Off, Suspended, Unknown
    maintenance_mode: bool = False
    sessions: int = 0
    metrics: ResourceMetrics = field(default_factory=ResourceMetrics)
    agent_version: Optional[str] = None
    os_type: Optional[str] = None
    fault_state: Optional[str] = None

    @property
    def status(self) -> HealthStatus:
        if self.maintenance_mode:
            return HealthStatus.WARNING
        if self.registration_state != "Registered":
            return HealthStatus.CRITICAL
        if self.fault_state and self.fault_state != "None":
            return HealthStatus.WARNING
        return HealthStatus.OK


@dataclass
class CitrixDeliveryGroup:
    name: str
    description: Optional[str] = None
    enabled: bool = True
    in_maintenance: bool = False
    total_machines: int = 0
    registered_machines: int = 0
    machines_with_load: int = 0
    sessions_active: int = 0
    sessions_disconnected: int = 0
    machines: list[CitrixMachine] = field(default_factory=list)

    @property
    def status(self) -> HealthStatus:
        if not self.enabled or self.in_maintenance:
            return HealthStatus.WARNING
        if self.total_machines == 0:
            return HealthStatus.UNKNOWN
        unregistered = self.total_machines - self.registered_machines
        ratio = unregistered / self.total_machines
        if ratio >= 0.5:
            return HealthStatus.CRITICAL
        if ratio > 0:
            return HealthStatus.WARNING
        return HealthStatus.OK


@dataclass
class CitrixController:
    name: str
    state: str  # Active, On, Off, Failed, Unknown
    version: Optional[str] = None

    @property
    def status(self) -> HealthStatus:
        if self.state in ("Active", "On"):
            return HealthStatus.OK
        if self.state in ("Off", "Failed"):
            return HealthStatus.CRITICAL
        return HealthStatus.UNKNOWN


@dataclass
class CitrixSnapshot:
    collected_at: datetime
    site_name: str
    delivery_groups: list[CitrixDeliveryGroup] = field(default_factory=list)
    controllers: list[CitrixController] = field(default_factory=list)
    user_sessions: list[UserSession] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_active_sessions(self) -> int:
        return sum(g.sessions_active for g in self.delivery_groups)

    @property
    def overall_status(self) -> HealthStatus:
        if self.errors and not self.delivery_groups:
            return HealthStatus.UNKNOWN
        statuses = [g.status for g in self.delivery_groups] + [c.status for c in self.controllers]
        if not statuses:
            return HealthStatus.UNKNOWN
        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        if HealthStatus.WARNING in statuses:
            return HealthStatus.WARNING
        return HealthStatus.OK


# ── Unified snapshot ─────────────────────────────────────────────────────────

@dataclass
class MasterSnapshot:
    collected_at: datetime
    avd: Optional[AVDSnapshot] = None
    rds: Optional[RDSSnapshot] = None
    citrix: Optional[CitrixSnapshot] = None

    @property
    def overall_status(self) -> HealthStatus:
        platform_statuses = []
        for snap in (self.avd, self.rds, self.citrix):
            if snap is not None:
                platform_statuses.append(snap.overall_status)
        if not platform_statuses:
            return HealthStatus.UNKNOWN
        if HealthStatus.CRITICAL in platform_statuses:
            return HealthStatus.CRITICAL
        if HealthStatus.WARNING in platform_statuses:
            return HealthStatus.WARNING
        return HealthStatus.OK
