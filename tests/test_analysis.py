"""Tests for the best-practice analysers.

Each test builds the smallest snapshot that should trip a specific check and
asserts the finding fires (by title) at the expected severity. Run with:

    python -m pytest tests/test_analysis.py -q
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vdm.analysis import avd as avd_analyser
from vdm.analysis import citrix as citrix_analyser
from vdm.analysis import rds as rds_analyser
from vdm.analysis.base import Severity
from vdm.analysis.common import latest_version, os_eol, version_key
from vdm.models.metrics import (
    AVDHostPool,
    AVDSessionHost,
    AVDSnapshot,
    CitrixController,
    CitrixDeliveryGroup,
    CitrixMachine,
    CitrixSnapshot,
    HealthStatus,
    RDSHost,
    RDSSnapshot,
    ResourceMetrics,
    SessionState,
    UserSession,
)

NOW = datetime.now(timezone.utc)


def _titles(findings, severity=None):
    return {f.title for f in findings if severity is None or f.severity == severity}


def _find(findings, title):
    return next(f for f in findings if f.title == title)


# ── common helpers ───────────────────────────────────────────────────────────

def test_version_key_orders_numerically():
    assert version_key("1.0.10000") > version_key("1.0.7982.1500")
    assert latest_version(["1.0.7982", "1.0.10000", "1.0.7900"]) == "1.0.10000"


def test_os_eol_detects_legacy_and_passes_current():
    assert os_eol("6.3.9600") is not None          # 2012 R2 build
    assert os_eol("Windows Server 2012 R2") is not None
    assert os_eol("Windows 7 Enterprise") is not None
    assert os_eol("10.0.22631.4317") is None        # Windows 11 23H2
    assert os_eol("Windows Server 2022") is None
    assert os_eol(None) is None


# ── AVD ──────────────────────────────────────────────────────────────────────

def _avd_host(name, **kw):
    defaults = dict(
        host_pool="hp", status=HealthStatus.OK, allow_new_sessions=True,
        sessions=1, max_sessions=10, agent_version="1.0.7982.1500",
        os_version="10.0.22631.4317", last_heartbeat=NOW,
    )
    defaults.update(kw)
    return AVDSessionHost(name=name, **defaults)


def _avd_snap(hosts, **pool_kw):
    pool = AVDHostPool(name="hp", resource_group="rg",
                       load_balancer_type="BreadthFirst", hosts=hosts, **pool_kw)
    return AVDSnapshot(collected_at=NOW, subscription_id="sub", host_pools=[pool])


def test_avd_whole_pool_drained_is_critical():
    snap = _avd_snap([_avd_host("h1", allow_new_sessions=False),
                      _avd_host("h2", allow_new_sessions=False)])
    f = _find(avd_analyser.analyse(snap), "Entire host pool is drained")
    assert f.severity == Severity.CRITICAL


def test_avd_stale_heartbeat_while_accepting_is_critical():
    snap = _avd_snap([_avd_host("h1", last_heartbeat=NOW - timedelta(minutes=40)),
                      _avd_host("h2")])
    f = _find(avd_analyser.analyse(snap), "Session host heartbeat is stale")
    assert f.severity == Severity.CRITICAL


def test_avd_eol_os_is_security_critical():
    snap = _avd_snap([_avd_host("h1", os_version="6.3.9600"), _avd_host("h2")])
    f = _find(avd_analyser.analyse(snap), "Session host on out-of-support OS")
    assert f.severity == Severity.CRITICAL


def test_avd_disk_pressure_flagged():
    snap = _avd_snap([
        _avd_host("h1", metrics=ResourceMetrics(disk_percent=92.0)),
        _avd_host("h2"),
    ])
    assert "Session host Disk critical" in _titles(avd_analyser.analyse(snap))


def test_avd_image_drift_warns():
    snap = _avd_snap([_avd_host("h1", os_version="10.0.22631.4317"),
                      _avd_host("h2", os_version="10.0.22621.3958")])
    assert "Mixed OS builds in host pool" in _titles(avd_analyser.analyse(snap))


def test_avd_disconnected_sprawl_warns():
    snap = _avd_snap([_avd_host("h1"), _avd_host("h2")],
                     active_sessions=10, disconnected_sessions=8)
    assert "High proportion of disconnected sessions" in _titles(avd_analyser.analyse(snap))


def test_avd_clean_pool_has_no_actionable_findings():
    snap = _avd_snap([_avd_host("h1"), _avd_host("h2")],
                     active_sessions=2, disconnected_sessions=0)
    actionable = [f for f in avd_analyser.analyse(snap) if not f.passed]
    assert actionable == [], [f.title for f in actionable]


# ── RDS ──────────────────────────────────────────────────────────────────────

def _rds_host(name, **kw):
    defaults = dict(status=HealthStatus.OK, active_sessions=5, max_sessions=20,
                    metrics=ResourceMetrics(), os_version="Windows Server 2022")
    defaults.update(kw)
    return RDSHost(hostname=name, **defaults)


def _rds_snap(hosts, sessions=None):
    return RDSSnapshot(collected_at=NOW, farm_name="farm", session_hosts=hosts,
                       user_sessions=sessions or [])


def test_rds_eol_os_is_security_critical():
    snap = _rds_snap([_rds_host("r1", os_version="Windows Server 2012 R2"),
                      _rds_host("r2")])
    f = _find(rds_analyser.analyse(snap), "Session host on out-of-support OS")
    assert f.severity == Severity.CRITICAL


def test_rds_oversubscription_warns():
    snap = _rds_snap([_rds_host("r1", active_sessions=30, max_sessions=25),
                      _rds_host("r2")])
    assert "Session host is oversubscribed" in _titles(rds_analyser.analyse(snap))


def test_rds_stale_idle_sessions_warn():
    sessions = [
        UserSession(f"user{i}", SessionState.DISCONNECTED, host="r1", idle_minutes=300)
        for i in range(6)
    ]
    snap = _rds_snap([_rds_host("r1"), _rds_host("r2")], sessions=sessions)
    assert "Stale disconnected sessions consuming resources" in _titles(
        rds_analyser.analyse(snap))


def test_rds_few_idle_sessions_do_not_warn():
    sessions = [
        UserSession("u1", SessionState.DISCONNECTED, host="r1", idle_minutes=300),
        UserSession("u2", SessionState.DISCONNECTED, host="r1", idle_minutes=300),
    ]
    snap = _rds_snap([_rds_host("r1"), _rds_host("r2")], sessions=sessions)
    assert "Stale disconnected sessions consuming resources" not in _titles(
        rds_analyser.analyse(snap))


# ── Citrix ───────────────────────────────────────────────────────────────────

def _vda(name, **kw):
    defaults = dict(delivery_group="DG", catalog="cat",
                    registration_state="Registered", power_state="On",
                    os_type="Windows 2022")
    defaults.update(kw)
    return CitrixMachine(name=name, **defaults)


def _ctx_snap(machines, controllers=None, **dg_kw):
    reg = sum(1 for m in machines if m.registration_state == "Registered")
    dg = CitrixDeliveryGroup(
        name="DG", enabled=True,
        total_machines=len(machines), registered_machines=reg,
        machines=machines, **dg_kw,
    )
    return CitrixSnapshot(
        collected_at=NOW, site_name="site",
        delivery_groups=[dg],
        controllers=controllers or [
            CitrixController("ddc1", state="Active", version="7.2402.0.0"),
            CitrixController("ddc2", state="Active", version="7.2402.0.0"),
        ],
    )


def test_citrix_vda_fault_state_is_critical():
    snap = _ctx_snap([_vda("v1", registration_state="Unregistered",
                            fault_state="FailedToStart", sessions=0),
                      _vda("v2"), _vda("v3")])
    f = _find(citrix_analyser.analyse(snap), "VDAs reporting fault states")
    assert f.severity == Severity.CRITICAL


def test_citrix_power_waste_warns():
    snap = _ctx_snap([_vda("v1", registration_state="Unregistered",
                            power_state="On", sessions=0),
                      _vda("v2"), _vda("v3")])
    assert "Powered-on VDAs serving no sessions" in _titles(citrix_analyser.analyse(snap))


def test_citrix_stuck_maintenance_warns():
    snap = _ctx_snap([_vda("v1", maintenance_mode=True), _vda("v2"), _vda("v3")])
    assert "Individual VDAs left in maintenance mode" in _titles(
        citrix_analyser.analyse(snap))


def test_citrix_controller_version_skew_warns():
    snap = _ctx_snap(
        [_vda("v1"), _vda("v2")],
        controllers=[CitrixController("ddc1", state="Active", version="7.2402.0.0"),
                     CitrixController("ddc2", state="Active", version="7.2311.0.0")],
    )
    assert "Delivery Controllers on mixed versions" in _titles(
        citrix_analyser.analyse(snap))


def test_citrix_eol_vda_os_is_security_critical():
    snap = _ctx_snap([_vda("v1", os_type="Windows Server 2012 R2"),
                      _vda("v2"), _vda("v3")])
    f = _find(citrix_analyser.analyse(snap), "VDAs on out-of-support OS")
    assert f.severity == Severity.CRITICAL


def test_citrix_disconnected_sprawl_warns():
    snap = _ctx_snap([_vda("v1"), _vda("v2"), _vda("v3")],
                     sessions_active=10, sessions_disconnected=8)
    assert "High proportion of disconnected sessions" in _titles(
        citrix_analyser.analyse(snap))
