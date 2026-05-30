"""Mock snapshot fixtures for testing and dashboard demo."""

from datetime import datetime, timedelta, timezone

from vdm.models.metrics import (
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
                        os_version="10.0.22631.4317",
                        metrics=ResourceMetrics(cpu_percent=45.2, memory_percent=67.8, disk_percent=58.0),
                        last_heartbeat=NOW - timedelta(minutes=1),
                    ),
                    AVDSessionHost(
                        name="avdhost-prod-02",
                        host_pool="hp-prod-pool-01",
                        status=HealthStatus.OK,
                        allow_new_sessions=True,
                        sessions=16,
                        max_sessions=20,
                        agent_version="1.0.7982.1500",
                        os_version="10.0.22631.4317",
                        # Reports healthy + accepting, but the agent went silent 38m ago.
                        metrics=ResourceMetrics(cpu_percent=78.1, memory_percent=82.3, disk_percent=93.5),
                        last_heartbeat=NOW - timedelta(minutes=38),
                    ),
                    AVDSessionHost(
                        name="avdhost-prod-03",
                        host_pool="hp-prod-pool-01",
                        status=HealthStatus.WARNING,
                        allow_new_sessions=False,
                        sessions=12,
                        max_sessions=20,
                        agent_version="1.0.7900.1000",
                        os_version="10.0.22621.3958",  # older build than peers → image drift
                        metrics=ResourceMetrics(cpu_percent=91.4, memory_percent=89.0, disk_percent=70.0),
                        last_heartbeat=NOW - timedelta(minutes=2),
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
                        os_version="6.3.9600",  # Server 2012 R2 — out of support
                        metrics=ResourceMetrics(cpu_percent=None, memory_percent=None),
                        last_heartbeat=NOW - timedelta(hours=6),
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
                max_sessions=30,
                metrics=ResourceMetrics(cpu_percent=58.4, memory_percent=72.1, disk_percent=41.2),
                os_version="Windows Server 2022 Datacenter",
                uptime_hours=312.5,
            ),
            RDSHost(
                hostname="rdsh02.corp.local",
                status=HealthStatus.WARNING,
                active_sessions=28,
                disconnected_sessions=2,
                max_sessions=25,  # 28 active > 25 max → oversubscribed
                metrics=ResourceMetrics(cpu_percent=88.3, memory_percent=91.4, disk_percent=65.0),
                os_version="Windows Server 2022 Datacenter",
                uptime_hours=720.0,
            ),
            RDSHost(
                hostname="rdsh03.corp.local",
                status=HealthStatus.OFFLINE,
                active_sessions=0,
                disconnected_sessions=0,
                max_sessions=25,
                metrics=ResourceMetrics(),
                os_version="Windows Server 2012 R2",  # out of support
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
            UserSession("dave", SessionState.ACTIVE, host="rdsh01.corp.local", idle_minutes=2),
            UserSession("eve", SessionState.DISCONNECTED, host="rdsh02.corp.local", idle_minutes=510),
            UserSession("frank", SessionState.DISCONNECTED, host="rdsh01.corp.local", idle_minutes=288),
            UserSession("grace", SessionState.DISCONNECTED, host="rdsh01.corp.local", idle_minutes=372),
            UserSession("heidi", SessionState.DISCONNECTED, host="rdsh02.corp.local", idle_minutes=265),
            UserSession("ivan", SessionState.DISCONNECTED, host="rdsh01.corp.local", idle_minutes=640),
            UserSession("judy", SessionState.DISCONNECTED, host="rdsh02.corp.local", idle_minutes=255),
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
                        os_type="Windows 11",
                        agent_version="2402.0.0",
                        metrics=ResourceMetrics(cpu_percent=34.0, memory_percent=61.0),
                    ),
                    CitrixMachine(
                        name="ctx-win11-09",
                        delivery_group="DG-Desktop-Win11",
                        catalog="CAT-Win11",
                        registration_state="Registered",
                        power_state="On",
                        maintenance_mode=True,  # left in maintenance after patching
                        sessions=0,
                        os_type="Windows 11",
                        agent_version="2402.0.0",
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
                        os_type="Windows Server 2012 R2",  # out of support
                    ),
                ],
            ),
        ],
        controllers=[
            CitrixController("ddc01.corp.local", state="Active", version="7.2402.0.0"),
            CitrixController("ddc02.corp.local", state="Active", version="7.2311.0.0"),  # upgrade stalled
        ],
        user_sessions=[
            UserSession("frank", SessionState.ACTIVE, host="ctx-win11-01"),
            UserSession("grace", SessionState.DISCONNECTED, host="ctx-apps-03"),
        ],
    )


def make_gpu_snapshot():
    from datetime import datetime, timezone
    from vdm.models.gpu import (
        GPUSnapshot, HostGPUData, PhysicalGPU, VGPUInstance, VGPUProfile, GPUEngine,
    )
    now = datetime.now(timezone.utc)

    def profile(name): return VGPUProfile.parse(name)

    return GPUSnapshot(
        collected_at=now,
        hosts={
            # AVD session host — A16 GPU, 3 healthy slices, 1 saturated
            "avdhost-prod-01": HostGPUData(
                hostname="avdhost-prod-01", platform="avd",
                has_nvidia=True, has_vgpu=True,
                physical_gpus=[PhysicalGPU(
                    index=0, name="NVIDIA A16",
                    total_memory_mb=16384, used_memory_mb=12800,
                    gpu_util_pct=71.0, mem_util_pct=78.0,
                    encoder_util_pct=42.0, decoder_util_pct=18.0,
                    temperature_c=74.0, power_draw_w=210.0, power_limit_w=250.0,
                    driver_version="535.129.03",
                    vgpu_instances=[
                        VGPUInstance(
                            instance_id="vgpu-0001", profile=profile("GRID A16-4Q"),
                            gpu_index=0, vm_name="avd-vm-alice",
                            fb_used_mb=2100, fb_total_mb=4096,
                            sm_util_pct=38.0, mem_util_pct=52.0,
                            encoder_util_pct=45.0, decoder_util_pct=12.0,
                        ),
                        VGPUInstance(
                            instance_id="vgpu-0002", profile=profile("GRID A16-4Q"),
                            gpu_index=0, vm_name="avd-vm-bob",
                            fb_used_mb=3850, fb_total_mb=4096,  # saturated!
                            sm_util_pct=91.0, mem_util_pct=94.0,
                            encoder_util_pct=88.0, decoder_util_pct=22.0,
                        ),
                        VGPUInstance(
                            instance_id="vgpu-0003", profile=profile("GRID A16-4Q"),
                            gpu_index=0, vm_name="avd-vm-carol",
                            fb_used_mb=310, fb_total_mb=4096,   # idle / oversized
                            sm_util_pct=3.0, mem_util_pct=8.0,
                            encoder_util_pct=4.0, decoder_util_pct=1.0,
                        ),
                        VGPUInstance(
                            instance_id="vgpu-0004", profile=profile("GRID A16-4Q"),
                            gpu_index=0, vm_name="avd-vm-dave",
                            fb_used_mb=1900, fb_total_mb=4096,
                            sm_util_pct=28.0, mem_util_pct=46.0,
                            encoder_util_pct=31.0, decoder_util_pct=8.0,
                        ),
                    ],
                )],
                collected_at=now,
            ),
            # RDS session host — T4, mixed B and Q profiles, one Q-profile user doing Office
            "rdsh01.corp.local": HostGPUData(
                hostname="rdsh01.corp.local", platform="rds",
                has_nvidia=True, has_vgpu=True,
                physical_gpus=[PhysicalGPU(
                    index=0, name="NVIDIA T4",
                    total_memory_mb=16384, used_memory_mb=8192,
                    gpu_util_pct=55.0, mem_util_pct=50.0,
                    encoder_util_pct=38.0, decoder_util_pct=10.0,
                    temperature_c=68.0, power_draw_w=55.0, power_limit_w=70.0,
                    driver_version="535.129.03",
                    vgpu_instances=[
                        VGPUInstance(
                            instance_id="vgpu-t4-01", profile=profile("GRID T4-2B"),
                            gpu_index=0, vm_name="rdsh-session-101",
                            fb_used_mb=820, fb_total_mb=2048,
                            sm_util_pct=22.0, mem_util_pct=40.0,
                            encoder_util_pct=29.0, decoder_util_pct=5.0,
                        ),
                        VGPUInstance(
                            instance_id="vgpu-t4-02", profile=profile("GRID T4-4Q"),  # Q for Office user!
                            gpu_index=0, vm_name="rdsh-session-102",
                            fb_used_mb=480, fb_total_mb=4096,
                            sm_util_pct=6.0, mem_util_pct=12.0,  # barely using it
                            encoder_util_pct=8.0, decoder_util_pct=2.0,
                        ),
                        VGPUInstance(
                            instance_id="vgpu-t4-03", profile=profile("GRID T4-2B"),
                            gpu_index=0, vm_name="rdsh-session-103",
                            fb_used_mb=950, fb_total_mb=2048,
                            sm_util_pct=44.0, mem_util_pct=46.0,
                            encoder_util_pct=51.0, decoder_util_pct=9.0,
                        ),
                        VGPUInstance(
                            instance_id="vgpu-t4-04", profile=profile("GRID T4-2B"),
                            gpu_index=0, vm_name="rdsh-session-104",
                            fb_used_mb=1100, fb_total_mb=2048,
                            sm_util_pct=53.0, mem_util_pct=54.0,
                            encoder_util_pct=61.0, decoder_util_pct=11.0,
                        ),
                    ],
                )],
                top_gpu_processes=[
                    GPUEngine("3D", 61.0, pid=4812, process_name="AutoCAD"),
                ],
                collected_at=now,
            ),
            # Citrix VDA — A10, hot GPU running render workloads
            "ctx-win11-01": HostGPUData(
                hostname="ctx-win11-01", platform="citrix",
                has_nvidia=True, has_vgpu=True,
                physical_gpus=[PhysicalGPU(
                    index=0, name="NVIDIA A10",
                    total_memory_mb=24576, used_memory_mb=18000,
                    gpu_util_pct=83.0, mem_util_pct=73.0,
                    encoder_util_pct=22.0, decoder_util_pct=8.0,
                    temperature_c=79.0, power_draw_w=135.0, power_limit_w=150.0,
                    driver_version="535.129.03",
                    vgpu_instances=[
                        VGPUInstance(
                            instance_id="vgpu-a10-01", profile=profile("GRID A10-8Q"),
                            gpu_index=0, vm_name="ctx-session-frank",
                            fb_used_mb=6900, fb_total_mb=8192,
                            sm_util_pct=77.0, mem_util_pct=84.0,
                            encoder_util_pct=19.0, decoder_util_pct=7.0,
                        ),
                        VGPUInstance(
                            instance_id="vgpu-a10-02", profile=profile("GRID A10-8Q"),
                            gpu_index=0, vm_name="ctx-session-heidi",
                            fb_used_mb=7800, fb_total_mb=8192,
                            sm_util_pct=88.0, mem_util_pct=95.0,  # saturated
                            encoder_util_pct=25.0, decoder_util_pct=9.0,
                        ),
                        VGPUInstance(
                            instance_id="vgpu-a10-03", profile=profile("GRID A10-8Q"),
                            gpu_index=0, vm_name="ctx-session-ivan",
                            fb_used_mb=3200, fb_total_mb=8192,
                            sm_util_pct=41.0, mem_util_pct=39.0,
                            encoder_util_pct=18.0, decoder_util_pct=5.0,
                        ),
                    ],
                )],
                collected_at=now,
            ),
        },
    )


def make_master_snapshot() -> MasterSnapshot:
    return MasterSnapshot(
        collected_at=NOW,
        avd=make_avd_snapshot(),
        rds=make_rds_snapshot(),
        citrix=make_citrix_snapshot(),
        gpu=make_gpu_snapshot(),
    )
