"""Mock snapshot fixtures for testing and dashboard demo."""

from datetime import datetime, timezone

from avd_masters.models.metrics import (
    AVDHostPool,
    AVDSessionHost,
    AVDSnapshot,
    CitrixController,
    CitrixDeliveryGroup,
    CitrixMachine,
    CitrixSnapshot,
    HealthStatus,
    MasterSnapshot,
    RDSBroker,
    RDSHost,
    RDSLicenseInfo,
    RDSSnapshot,
    ResourceMetrics,
    SessionState,
    UserSession,
)

NOW = datetime.now(timezone.utc)


def make_avd_snapshot() -> AVDSnapshot:
    return AVDSnapshot(
        collected_at=NOW,
        subscription_id="demo-sub-id",
        host_pools=[
            AVDHostPool(
                name="hp-prod-pool-01",
                resource_group="rg-avd-prod",
                load_balancer_type="BreadthFirst",
                active_sessions=42,
                disconnected_sessions=5,
                hosts=[
                    AVDSessionHost(
                        name="avdhost-prod-01",
                        host_pool="hp-prod-pool-01",
                        status=HealthStatus.OK,
                        allow_new_sessions=True,
                        sessions=14,
                        max_sessions=20,
                        agent_version="1.0.7982.1500",
                        metrics=ResourceMetrics(cpu_percent=45.2, memory_percent=67.8),
                    ),
                    AVDSessionHost(
                        name="avdhost-prod-02",
                        host_pool="hp-prod-pool-01",
                        status=HealthStatus.OK,
                        allow_new_sessions=True,
                        sessions=16,
                        max_sessions=20,
                        agent_version="1.0.7982.1500",
                        metrics=ResourceMetrics(cpu_percent=78.1, memory_percent=82.3),
                    ),
                    AVDSessionHost(
                        name="avdhost-prod-03",
                        host_pool="hp-prod-pool-01",
                        status=HealthStatus.WARNING,
                        allow_new_sessions=False,
                        sessions=12,
                        max_sessions=20,
                        agent_version="1.0.7900.1000",
                        metrics=ResourceMetrics(cpu_percent=91.4, memory_percent=89.0),
                    ),
                ],
            ),
            AVDHostPool(
                name="hp-dev-pool-01",
                resource_group="rg-avd-dev",
                load_balancer_type="DepthFirst",
                active_sessions=3,
                disconnected_sessions=1,
                hosts=[
                    AVDSessionHost(
                        name="avdhost-dev-01",
                        host_pool="hp-dev-pool-01",
                        status=HealthStatus.CRITICAL,
                        allow_new_sessions=False,
                        sessions=0,
                        max_sessions=10,
                        agent_version="1.0.7800.1000",
                        metrics=ResourceMetrics(cpu_percent=None, memory_percent=None),
                    ),
                    AVDSessionHost(
                        name="avdhost-dev-02",
                        host_pool="hp-dev-pool-01",
                        status=HealthStatus.OK,
                        allow_new_sessions=True,
                        sessions=3,
                        max_sessions=10,
                        metrics=ResourceMetrics(cpu_percent=22.0, memory_percent=55.0),
                    ),
                ],
            ),
        ],
        user_sessions=[
            UserSession("alice@corp.com", SessionState.ACTIVE, host="avdhost-prod-01"),
            UserSession("bob@corp.com", SessionState.DISCONNECTED, host="avdhost-prod-02"),
            UserSession("carol@corp.com", SessionState.ACTIVE, host="avdhost-prod-01"),
        ],
    )


def make_rds_snapshot() -> RDSSnapshot:
    return RDSSnapshot(
        collected_at=NOW,
        farm_name="Production RDS Farm",
        session_hosts=[
            RDSHost(
                hostname="rdsh01.corp.local",
                status=HealthStatus.OK,
                active_sessions=22,
                disconnected_sessions=4,
                metrics=ResourceMetrics(cpu_percent=58.4, memory_percent=72.1, disk_percent=41.2),
                uptime_hours=312.5,
            ),
            RDSHost(
                hostname="rdsh02.corp.local",
                status=HealthStatus.WARNING,
                active_sessions=28,
                disconnected_sessions=2,
                metrics=ResourceMetrics(cpu_percent=88.3, memory_percent=91.4, disk_percent=65.0),
                uptime_hours=720.0,
            ),
            RDSHost(
                hostname="rdsh03.corp.local",
                status=HealthStatus.OFFLINE,
                active_sessions=0,
                disconnected_sessions=0,
                metrics=ResourceMetrics(),
                uptime_hours=None,
            ),
        ],
        brokers=[
            RDSBroker("rdbroker01.corp.local", HealthStatus.OK, is_active=True),
        ],
        license_info=RDSLicenseInfo(
            server="rdlicense01.corp.local",
            total_cals=100,
            used_cals=83,
            available_cals=17,
        ),
        user_sessions=[
            UserSession("dave", SessionState.ACTIVE, host="rdsh01.corp.local"),
            UserSession("eve", SessionState.DISCONNECTED, host="rdsh02.corp.local"),
        ],
    )


def make_citrix_snapshot() -> CitrixSnapshot:
    return CitrixSnapshot(
        collected_at=NOW,
        site_name="Production Citrix Site",
        delivery_groups=[
            CitrixDeliveryGroup(
                name="DG-Desktop-Win11",
                enabled=True,
                total_machines=20,
                registered_machines=20,
                sessions_active=15,
                sessions_disconnected=3,
                machines=[
                    CitrixMachine(
                        name="ctx-win11-01",
                        delivery_group="DG-Desktop-Win11",
                        catalog="CAT-Win11",
                        registration_state="Registered",
                        power_state="On",
                        sessions=2,
                        metrics=ResourceMetrics(cpu_percent=34.0, memory_percent=61.0),
                    ),
                ],
            ),
            CitrixDeliveryGroup(
                name="DG-Apps-Office",
                enabled=True,
                total_machines=10,
                registered_machines=8,
                sessions_active=24,
                sessions_disconnected=1,
                machines=[
                    CitrixMachine(
                        name="ctx-apps-03",
                        delivery_group="DG-Apps-Office",
                        catalog="CAT-Apps",
                        registration_state="Unregistered",
                        power_state="On",
                        fault_state="FailedToStart",
                        sessions=0,
                    ),
                    CitrixMachine(
                        name="ctx-apps-07",
                        delivery_group="DG-Apps-Office",
                        catalog="CAT-Apps",
                        registration_state="Unregistered",
                        power_state="On",
                        sessions=0,
                    ),
                ],
            ),
        ],
        controllers=[
            CitrixController("ddc01.corp.local", state="Active", version="7.2402.0.0"),
            CitrixController("ddc02.corp.local", state="Active", version="7.2402.0.0"),
        ],
        user_sessions=[
            UserSession("frank", SessionState.ACTIVE, host="ctx-win11-01"),
            UserSession("grace", SessionState.DISCONNECTED, host="ctx-apps-03"),
        ],
    )


def make_master_snapshot() -> MasterSnapshot:
    return MasterSnapshot(
        collected_at=NOW,
        avd=make_avd_snapshot(),
        rds=make_rds_snapshot(),
        citrix=make_citrix_snapshot(),
    )
