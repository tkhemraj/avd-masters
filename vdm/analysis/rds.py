"""Best-practice analysis for On-Premises Terminal Services (RDS)."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from ..models.metrics import HealthStatus, RDSSnapshot, SessionState
from .base import Category, Finding, Severity
from .common import os_eol, summarize_names

_DEFAULTS = {
    "min_session_hosts":       2,      # HA: at least 2 RDSH servers
    "min_brokers":             2,      # HA: at least 2 Connection Brokers
    "cal_warn_pct":           80.0,    # CAL utilisation warning
    "cal_crit_pct":           95.0,    # CAL utilisation critical
    "cpu_warn_pct":           75.0,
    "cpu_crit_pct":           90.0,
    "mem_warn_pct":           85.0,
    "mem_crit_pct":           95.0,
    "disk_warn_pct":          80.0,
    "disk_crit_pct":          95.0,
    "max_uptime_days":        30.0,    # flag hosts up > 30 days (patch hygiene)
    "disconnected_ratio_warn": 0.30,   # warn if >30% of sessions are disconnected
    "capacity_headroom_pct":  20.0,    # total farm should have ≥20% spare capacity
    "idle_disconnect_minutes": 240,    # flag disconnected sessions idle longer than this
    "idle_session_warn_count": 5,      # ...once this many are stale
}


def analyse(snap: RDSSnapshot, cfg: Optional[dict] = None) -> list[Finding]:
    t = {**_DEFAULTS, **(cfg or {})}
    findings: list[Finding] = []

    _farm_availability(snap, t, findings)
    _broker_redundancy(snap, t, findings)
    _licensing(snap, t, findings)
    _farm_capacity(snap, t, findings)
    _disconnected_session_ratio(snap, t, findings)
    _stale_idle_sessions(snap, t, findings)
    for host in snap.session_hosts:
        _host_resources(snap.farm_name, host, t, findings)
        _host_uptime(snap.farm_name, host, t, findings)
        _host_os_currency(host, findings)
        _host_oversubscribed(host, findings)

    return findings


def _farm_availability(snap, t, findings):
    total = len(snap.session_hosts)
    online = sum(1 for h in snap.session_hosts
                 if h.status not in (HealthStatus.OFFLINE, HealthStatus.CRITICAL))
    minimum = t["min_session_hosts"]

    if total < minimum:
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="Farm below minimum session host count",
            detail=(
                f"Farm '{snap.farm_name}' has only {total} session host(s), "
                f"minimum recommended is {minimum}. "
                "A single host failure leaves users with no farm capacity."
            ),
            recommendation=(
                f"Add at least {minimum - total} more session host(s) to achieve "
                "N+1 redundancy across the farm."
            ),
        ))
    elif online < total:
        offline_names = [h.hostname for h in snap.session_hosts
                         if h.status in (HealthStatus.OFFLINE, HealthStatus.CRITICAL)]
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.WARNING,
            category=Category.AVAILABILITY,
            title="One or more session hosts degraded or offline",
            detail=(
                f"{len(offline_names)} of {total} hosts are not fully available: "
                + ", ".join(offline_names)
            ),
            recommendation=(
                "Investigate and restore offline hosts. "
                "Verify remaining hosts have enough capacity to absorb load."
            ),
        ))
    else:
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.PASS,
            category=Category.AVAILABILITY,
            title="All session hosts online",
            detail=f"All {total} session hosts in '{snap.farm_name}' are reachable.",
            recommendation="",
        ))


def _broker_redundancy(snap, t, findings):
    total = len(snap.brokers)
    active = sum(1 for b in snap.brokers if b.status == HealthStatus.OK)
    minimum = t["min_brokers"]

    if total < minimum:
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="Insufficient RD Connection Brokers for HA",
            detail=(
                f"Farm has {total} broker(s), minimum recommended is {minimum}. "
                "A single broker failure will prevent new session connections "
                "and break session reconnection for all users."
            ),
            recommendation=(
                "Deploy a second RD Connection Broker and configure "
                "SQL Server high availability for the session broker database. "
                "See: docs.microsoft.com/en-us/windows-server/remote/remote-desktop-services/"
                "rds-connection-broker-cluster"
            ),
        ))
    elif active < total:
        down = [b.hostname for b in snap.brokers if b.status != HealthStatus.OK]
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="RD Connection Broker(s) unreachable",
            detail=f"Brokers not responding: {', '.join(down)}",
            recommendation=(
                "Investigate the broker service (Remote Desktop Connection Broker role) "
                "on the affected servers. Check Event Viewer for errors under "
                "Applications and Services Logs > Microsoft > Windows > "
                "TerminalServices-SessionBroker."
            ),
        ))
    else:
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.PASS,
            category=Category.AVAILABILITY,
            title="Connection Brokers healthy and redundant",
            detail=f"{active} broker(s) active and reachable.",
            recommendation="",
        ))


def _licensing(snap, t, findings):
    if not snap.license_info:
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.INFO,
            category=Category.LICENSING,
            title="License server not monitored",
            detail="No RD Licensing server is configured for monitoring.",
            recommendation=(
                "Add license_server to the RDS config block to enable "
                "CAL utilisation tracking and alerting."
            ),
        ))
        return

    li = snap.license_info
    pct = li.utilization_percent

    if pct >= t["cal_crit_pct"]:
        findings.append(Finding(
            platform="RDS", resource=li.server,
            severity=Severity.CRITICAL,
            category=Category.LICENSING,
            title="RDS CAL pool critically full",
            detail=(
                f"{li.used_cals}/{li.total_cals} CALs issued ({pct:.1f}%). "
                f"Only {li.available_cals} CAL(s) remain. "
                "New connections will be refused once the pool is exhausted."
            ),
            recommendation=(
                "Purchase and install additional CALs immediately. "
                "Audit inactive CAL assignments and revoke any assigned to "
                "decommissioned devices or users via the RD Licensing Manager."
            ),
        ))
    elif pct >= t["cal_warn_pct"]:
        findings.append(Finding(
            platform="RDS", resource=li.server,
            severity=Severity.WARNING,
            category=Category.LICENSING,
            title="RDS CAL utilisation high",
            detail=(
                f"{li.used_cals}/{li.total_cals} CALs issued ({pct:.1f}%). "
                f"{li.available_cals} CAL(s) remaining."
            ),
            recommendation=(
                "Plan a CAL purchase to stay ahead of growth. "
                "Review license assignments and reclaim CALs from inactive users."
            ),
        ))
    else:
        findings.append(Finding(
            platform="RDS", resource=li.server,
            severity=Severity.PASS,
            category=Category.LICENSING,
            title="CAL utilisation within acceptable range",
            detail=f"{li.used_cals}/{li.total_cals} CALs used ({pct:.1f}%).",
            recommendation="",
        ))


def _farm_capacity(snap, t, findings):
    hosts = [h for h in snap.session_hosts
             if h.status not in (HealthStatus.OFFLINE,)]
    if not hosts:
        return

    total_active = sum(h.active_sessions for h in hosts)
    total_max = sum(h.max_sessions for h in hosts if h.max_sessions > 0)

    if total_max == 0:
        return

    used_pct = (total_active / total_max) * 100
    headroom_needed = t["capacity_headroom_pct"]

    if used_pct >= (100 - headroom_needed):
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.WARNING,
            category=Category.CAPACITY,
            title="Farm-wide session capacity headroom insufficient",
            detail=(
                f"Total active sessions: {total_active} / {total_max} max "
                f"({used_pct:.1f}% used). "
                f"Less than {headroom_needed:.0f}% headroom remains across the farm."
            ),
            recommendation=(
                "Add additional session hosts or reduce max sessions per host "
                "to ensure capacity for peak load and host failure scenarios."
            ),
        ))
    else:
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.PASS,
            category=Category.CAPACITY,
            title="Farm session capacity is adequate",
            detail=(
                f"{total_active}/{total_max} sessions used ({used_pct:.1f}%). "
                f"{100 - used_pct:.1f}% headroom available."
            ),
            recommendation="",
        ))


def _disconnected_session_ratio(snap, t, findings):
    total = sum(h.active_sessions + h.disconnected_sessions for h in snap.session_hosts)
    disconnected = sum(h.disconnected_sessions for h in snap.session_hosts)
    if total == 0:
        return

    ratio = disconnected / total
    warn_ratio = t["disconnected_ratio_warn"]

    if ratio >= warn_ratio:
        findings.append(Finding(
            platform="RDS", resource=snap.farm_name,
            severity=Severity.WARNING,
            category=Category.HYGIENE,
            title="High proportion of disconnected sessions",
            detail=(
                f"{disconnected} of {total} sessions ({ratio * 100:.1f}%) are disconnected. "
                f"Threshold: {warn_ratio * 100:.0f}%. "
                "Disconnected sessions consume server memory and CALs."
            ),
            recommendation=(
                "Configure a Group Policy session time limit: "
                "Computer Configuration > Policies > Administrative Templates > "
                "Windows Components > Remote Desktop Services > "
                "Set time limit for disconnected sessions. "
                "Recommended: 2–4 hours for knowledge workers."
            ),
        ))


def _host_resources(farm_name, host, t, findings):
    checks = [
        (host.metrics.cpu_percent,  "CPU",  t["cpu_warn_pct"],  t["cpu_crit_pct"]),
        (host.metrics.memory_percent, "Memory", t["mem_warn_pct"], t["mem_crit_pct"]),
        (host.metrics.disk_percent, "Disk (C:)", t["disk_warn_pct"], t["disk_crit_pct"]),
    ]
    for value, label, warn, crit in checks:
        if value is None:
            continue
        if value >= crit:
            findings.append(Finding(
                platform="RDS", resource=host.hostname,
                severity=Severity.CRITICAL,
                category=Category.PERFORMANCE,
                title=f"{label} critically high on session host",
                detail=(
                    f"{host.hostname} {label} at {value:.1f}% "
                    f"(critical threshold: {crit:.0f}%)."
                ),
                recommendation=(
                    f"Investigate high {label} consumers on {host.hostname}. "
                    "Consider draining sessions and rebooting if unresolved."
                    + (" Free up disk space or expand the volume." if "Disk" in label else "")
                ),
            ))
        elif value >= warn:
            findings.append(Finding(
                platform="RDS", resource=host.hostname,
                severity=Severity.WARNING,
                category=Category.PERFORMANCE,
                title=f"{label} elevated on session host",
                detail=f"{host.hostname} {label} at {value:.1f}% (warning: {warn:.0f}%).",
                recommendation=f"Monitor {label} trend on {host.hostname}.",
            ))


def _host_uptime(farm_name, host, t, findings):
    if host.uptime_hours is None:
        return
    uptime_days = host.uptime_hours / 24
    max_days = t["max_uptime_days"]

    if uptime_days > max_days:
        findings.append(Finding(
            platform="RDS", resource=host.hostname,
            severity=Severity.WARNING,
            category=Category.HYGIENE,
            title="Session host has not been rebooted recently",
            detail=(
                f"{host.hostname} has been running for {uptime_days:.0f} days "
                f"(threshold: {max_days:.0f} days). "
                "Extended uptime delays security patches and can lead to "
                "memory leaks and performance degradation over time."
            ),
            recommendation=(
                "Schedule a maintenance window to reboot this host during off-peak hours. "
                "Drain sessions first using Set-RDSessionHost or the RDS Manager console. "
                "Consider automating monthly maintenance reboots via Task Scheduler or SCCM."
            ),
        ))


def _host_os_currency(host, findings):
    eol = os_eol(host.os_version)
    if not eol:
        return
    name, eol_date = eol
    findings.append(Finding(
        platform="RDS", resource=host.hostname,
        severity=Severity.CRITICAL,
        category=Category.SECURITY,
        title="Session host on out-of-support OS",
        detail=(
            f"{host.hostname} is running {name} (reported: '{host.os_version}'), "
            f"which left Microsoft support on {eol_date}. "
            "It receives no security patches and is a direct attack surface for "
            "every user that logs on to it."
        ),
        recommendation=(
            "Migrate these workloads to a supported Windows Server release "
            "(2019/2022/2025). If migration is blocked, an ESU subscription is the "
            "only supported stopgap — but plan the rebuild."
        ),
    ))


def _host_oversubscribed(host, findings):
    """Active sessions above the configured per-host limit = brokering past capacity."""
    if host.max_sessions <= 0 or host.active_sessions <= host.max_sessions:
        return
    findings.append(Finding(
        platform="RDS", resource=host.hostname,
        severity=Severity.WARNING,
        category=Category.CAPACITY,
        title="Session host is oversubscribed",
        detail=(
            f"{host.hostname} has {host.active_sessions} active sessions against a "
            f"max of {host.max_sessions}. The broker has placed more users than the "
            "host is sized for, usually because peers are down or draining."
        ),
        recommendation=(
            "Restore drained/offline peers so the broker can rebalance, or raise the "
            "limit only if the host genuinely has CPU/RAM headroom. Sustained "
            "oversubscription degrades every session on the host."
        ),
    ))


def _stale_idle_sessions(snap, t, findings):
    """Disconnected sessions sitting idle for hours pin CALs, RAM and profile locks."""
    threshold = t["idle_disconnect_minutes"]
    stale = [
        s for s in snap.user_sessions
        if s.state in (SessionState.DISCONNECTED, SessionState.IDLE)
        and s.idle_minutes is not None
        and s.idle_minutes >= threshold
    ]
    if len(stale) < t["idle_session_warn_count"]:
        return
    worst = max(stale, key=lambda s: s.idle_minutes or 0)
    findings.append(Finding(
        platform="RDS", resource=snap.farm_name,
        severity=Severity.WARNING,
        category=Category.HYGIENE,
        title="Stale disconnected sessions consuming resources",
        detail=(
            f"{len(stale)} session(s) have been idle/disconnected for ≥"
            f"{threshold // 60}h (longest: {worst.username} on {worst.host or 'unknown'} "
            f"at {(worst.idle_minutes or 0) / 60:.1f}h). "
            "Each holds a CAL, a roaming profile lock and server memory."
        ),
        recommendation=(
            "Enforce 'End session when time limits are reached' with a disconnected "
            "session limit (GPO: RDS > Session Time Limits). Reset stragglers now with "
            "`Get-RDUserSession | ? SessionState -eq Disconnected | Invoke-RDUserLogoff`."
        ),
    ))
