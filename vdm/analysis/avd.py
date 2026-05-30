"""Best-practice analysis for Azure Virtual Desktop."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from ..models.metrics import AVDSnapshot, HealthStatus
from .base import Category, Finding, Severity
from .common import latest_version, os_eol, summarize_names

# Tunable thresholds — can be overridden via config["analysis"]["avd"]
_DEFAULTS = {
    "min_hosts_per_pool":          2,      # HA: minimum session hosts per pool
    "session_fill_warn_pct":      80.0,    # warn when host is >80% full
    "cpu_warn_pct":               75.0,
    "cpu_crit_pct":               90.0,
    "mem_warn_pct":               85.0,
    "mem_crit_pct":               95.0,
    "disk_warn_pct":              80.0,
    "disk_crit_pct":              90.0,
    "max_agent_versions_per_pool": 1,      # all hosts should run same agent
    "max_os_builds_per_pool":      1,      # all hosts should share one golden image
    "min_headroom_hosts":          1,      # pool must have ≥N available hosts
    "heartbeat_stale_minutes":    15,      # host is stale if no heartbeat in Nm
    "disconnected_ratio_warn":     0.30,   # warn if >30% of pool sessions are disconnected
}


def analyse(snap: AVDSnapshot, cfg: Optional[dict] = None) -> list[Finding]:
    t = {**_DEFAULTS, **(cfg or {})}
    findings: list[Finding] = []

    for pool in snap.host_pools:
        _pool_availability(pool, t, findings)
        _pool_drain_state(pool, findings)
        _pool_session_distribution(pool, t, findings)
        _pool_disconnected_sessions(pool, t, findings)
        _agent_version_currency(pool, t, findings)
        _image_consistency(pool, t, findings)
        for host in pool.hosts:
            _host_resources(pool.name, host, t, findings)
            _host_accepting_sessions(pool.name, host, findings)
            _host_heartbeat(pool.name, host, t, findings)
            _host_os_currency(pool.name, host, findings)

    return findings


def _pool_availability(pool, t, findings):
    total = len(pool.hosts)
    available = pool.available_hosts
    minimum = t["min_hosts_per_pool"]

    if total < minimum:
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="Host pool below minimum host count",
            detail=(
                f"Pool '{pool.name}' has {total} session host(s), "
                f"minimum recommended is {minimum}. "
                "A single host failure will take the entire pool offline."
            ),
            recommendation=(
                f"Add at least {minimum - total} more session host(s) to this pool "
                "to achieve N+1 redundancy."
            ),
        ))
    else:
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.PASS,
            category=Category.AVAILABILITY,
            title="Host pool has sufficient hosts",
            detail=f"{total} session hosts present (minimum {minimum}).",
            recommendation="",
        ))

    min_headroom = t["min_headroom_hosts"]
    if available < min_headroom:
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="No session hosts accepting new connections",
            detail=(
                f"Pool '{pool.name}' has {available} host(s) currently accepting new sessions "
                f"(minimum recommended: {min_headroom}). "
                "New user logons will fail or be queued indefinitely."
            ),
            recommendation=(
                "Check drained/unavailable hosts and restore them to service, "
                "or add additional hosts via the scaling plan."
            ),
        ))
    elif available < total:
        offline = [h.name for h in pool.hosts
                   if h.status in (HealthStatus.CRITICAL, HealthStatus.OFFLINE)
                   or not h.allow_new_sessions]
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.WARNING,
            category=Category.AVAILABILITY,
            title="Some hosts not accepting new sessions",
            detail=(
                f"{total - available} of {total} hosts are not accepting new connections: "
                + ", ".join(offline[:5])
                + ("…" if len(offline) > 5 else "")
            ),
            recommendation=(
                "Investigate drained or unhealthy hosts. "
                "If intentionally draining, ensure remaining capacity can absorb the load."
            ),
        ))


def _pool_session_distribution(pool, t, findings):
    if not pool.hosts:
        return

    fill_warn = t["session_fill_warn_pct"]
    overloaded = []
    for host in pool.hosts:
        if host.max_sessions > 0:
            pct = (host.sessions / host.max_sessions) * 100
            if pct >= fill_warn:
                overloaded.append((host.name, pct))

    if overloaded:
        worst_name, worst_pct = max(overloaded, key=lambda x: x[1])
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.WARNING,
            category=Category.CAPACITY,
            title="Session hosts nearing session capacity",
            detail=(
                f"{len(overloaded)} host(s) in pool '{pool.name}' are above "
                f"{fill_warn:.0f}% session capacity. "
                f"Worst: {worst_name} at {worst_pct:.1f}%."
            ),
            recommendation=(
                "Scale out the host pool, adjust the scaling plan trigger threshold, "
                "or reduce the per-host max session limit to leave headroom."
            ),
        ))

    # BreadthFirst pools: flag if sessions are heavily skewed to one host
    if pool.load_balancer_type == "BreadthFirst" and len(pool.hosts) > 1:
        session_counts = [h.sessions for h in pool.hosts if h.allow_new_sessions]
        if session_counts and max(session_counts) > 0:
            skew = max(session_counts) / (sum(session_counts) / len(session_counts))
            if skew > 2.5:
                findings.append(Finding(
                    platform="AVD", resource=pool.name,
                    severity=Severity.INFO,
                    category=Category.CONFIGURATION,
                    title="Session imbalance in BreadthFirst pool",
                    detail=(
                        f"Pool '{pool.name}' uses BreadthFirst load balancing but sessions "
                        f"are unevenly distributed (skew factor {skew:.1f}x). "
                        "This can indicate a host that rejoined mid-session."
                    ),
                    recommendation=(
                        "Review whether all hosts were available throughout the day. "
                        "Consider draining and re-enabling the skewed host during low-traffic."
                    ),
                ))


def _agent_version_currency(pool, t, findings):
    versions = Counter(
        h.agent_version for h in pool.hosts if h.agent_version
    )
    if not versions:
        return

    max_versions = t["max_agent_versions_per_pool"]
    latest = latest_version(versions)

    stale = [h.name for h in pool.hosts
             if h.agent_version and h.agent_version != latest]

    if len(versions) > max_versions:
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.WARNING,
            category=Category.CURRENCY,
            title="Mixed AVD agent versions in pool",
            detail=(
                f"Pool '{pool.name}' has {len(versions)} different agent versions: "
                + ", ".join(f"{v} ({c}x)" for v, c in versions.most_common())
                + f". Hosts not on latest ({latest}): "
                + ", ".join(stale[:5])
                + ("…" if len(stale) > 5 else "")
            ),
            recommendation=(
                "Update all session hosts to the latest AVD agent version. "
                "Reimage or run Windows Update on stale hosts during a maintenance window."
            ),
        ))
    else:
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.PASS,
            category=Category.CURRENCY,
            title="All hosts running consistent agent version",
            detail=f"All hosts in '{pool.name}' are on agent version {latest}.",
            recommendation="",
        ))


def _host_resources(pool_name, host, t, findings):
    checks = [
        (host.metrics.cpu_percent, "CPU",
         t["cpu_warn_pct"], t["cpu_crit_pct"]),
        (host.metrics.memory_percent, "Memory",
         t["mem_warn_pct"], t["mem_crit_pct"]),
        (host.metrics.disk_percent, "Disk",
         t["disk_warn_pct"], t["disk_crit_pct"]),
    ]
    # Disk pressure on an AVD host is usually the FSLogix container volume, not CPU/RAM.
    disk_rec = (
        "Free space on the FSLogix profile/Office container volume immediately — a full "
        "volume causes failed profile loads and temp-profile logons. Check for bloated "
        "VHDX files, orphaned containers, and the Windows update/CBS store."
    )
    for value, label, warn, crit in checks:
        if value is None:
            continue
        is_disk = label == "Disk"
        if value >= crit:
            findings.append(Finding(
                platform="AVD", resource=host.name,
                severity=Severity.CRITICAL,
                category=Category.PERFORMANCE,
                title=f"Session host {label} critical",
                detail=(
                    f"{host.name} (pool: {pool_name}) {label} is at {value:.1f}% "
                    f"(threshold: {crit:.0f}%). Active sessions will experience severe degradation."
                ),
                recommendation=disk_rec if is_disk else (
                    f"Drain this host immediately if {label} doesn't recover. "
                    "Investigate runaway processes or reduce the max session limit."
                ),
            ))
        elif value >= warn:
            findings.append(Finding(
                platform="AVD", resource=host.name,
                severity=Severity.WARNING,
                category=Category.PERFORMANCE,
                title=f"Session host {label} elevated",
                detail=(
                    f"{host.name} (pool: {pool_name}) {label} is at {value:.1f}% "
                    f"(threshold: {warn:.0f}%)."
                ),
                recommendation=(
                    f"Monitor {label} trend. Consider reducing max sessions on this host "
                    "or scaling out the pool."
                ),
            ))


def _host_accepting_sessions(pool_name, host, findings):
    if (host.status == HealthStatus.OK
            and not host.allow_new_sessions
            and host.sessions == 0):
        findings.append(Finding(
            platform="AVD", resource=host.name,
            severity=Severity.INFO,
            category=Category.CONFIGURATION,
            title="Healthy host not accepting new sessions with no active load",
            detail=(
                f"{host.name} (pool: {pool_name}) is healthy and idle "
                "but is not accepting new sessions. "
                "It may have been manually drained and forgotten."
            ),
            recommendation=(
                "Re-enable the host for new sessions in the Azure portal "
                "or via Set-AzWvdSessionHost -AllowNewSession $true."
            ),
        ))


def _pool_drain_state(pool, findings):
    """Whole pool drained — every host rejecting sessions, even if 'healthy'."""
    if not pool.hosts:
        return
    if all(not h.allow_new_sessions for h in pool.hosts):
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="Entire host pool is drained",
            detail=(
                f"All {len(pool.hosts)} host(s) in pool '{pool.name}' have "
                "AllowNewSession = false. The pool is effectively offline to new "
                "users regardless of host health — every logon will fail or queue."
            ),
            recommendation=(
                "Re-enable at least one host: "
                "Update-AzWvdSessionHost -AllowNewSession:$true. "
                "If a scaling plan drained the pool, check its schedule and ramp-up "
                "capacity threshold — a misconfigured off-peak window can drain everything."
            ),
        ))


def _pool_disconnected_sessions(pool, t, findings):
    """Disconnected sessions hold FSLogix profile mounts and licences open."""
    total = pool.active_sessions + pool.disconnected_sessions
    if total == 0:
        return
    ratio = pool.disconnected_sessions / total
    if ratio >= t["disconnected_ratio_warn"]:
        findings.append(Finding(
            platform="AVD", resource=pool.name,
            severity=Severity.WARNING,
            category=Category.HYGIENE,
            title="High proportion of disconnected sessions",
            detail=(
                f"{pool.disconnected_sessions} of {total} sessions "
                f"({ratio * 100:.0f}%) in pool '{pool.name}' are disconnected. "
                "Each holds an FSLogix profile disk mounted and consumes host memory, "
                "blocking clean host drains and scale-in."
            ),
            recommendation=(
                "Set disconnected and idle session time limits via host pool RDP "
                "properties or GPO (Remote Desktop Services > Session Time Limits). "
                "Typical: log off disconnected sessions after 1–4 hours."
            ),
        ))


def _host_heartbeat(pool_name, host, t, findings):
    """A host can report 'Available' while its agent has gone silent — a ghost host."""
    if host.last_heartbeat is None:
        return
    hb = host.last_heartbeat
    if hb.tzinfo is None:
        hb = hb.replace(tzinfo=timezone.utc)
    age_min = (datetime.now(timezone.utc) - hb).total_seconds() / 60
    stale_after = t["heartbeat_stale_minutes"]
    if age_min < stale_after:
        return

    accepting = host.allow_new_sessions and host.status == HealthStatus.OK
    findings.append(Finding(
        platform="AVD", resource=host.name,
        severity=Severity.CRITICAL if accepting else Severity.WARNING,
        category=Category.AVAILABILITY,
        title="Session host heartbeat is stale",
        detail=(
            f"{host.name} (pool: {pool_name}) last reported {age_min:.0f} min ago "
            f"(stale after {stale_after} min)."
            + (" It is still accepting new sessions — users will be brokered to a "
               "host whose agent may be dead, causing black-screen logons."
               if accepting else "")
        ),
        recommendation=(
            "Check the Remote Desktop Agent Loader (RDAgentBootLoader) and "
            "Azure Instance Metadata connectivity on the host. If unrecoverable, "
            "drain it (AllowNewSession:$false) and reimage."
        ),
    ))


def _host_os_currency(pool_name, host, findings):
    eol = os_eol(host.os_version)
    if not eol:
        return
    name, eol_date = eol
    findings.append(Finding(
        platform="AVD", resource=host.name,
        severity=Severity.CRITICAL,
        category=Category.SECURITY,
        title="Session host on out-of-support OS",
        detail=(
            f"{host.name} (pool: {pool_name}) reports OS '{host.os_version}' "
            f"({name}), which left Microsoft support on {eol_date}. "
            "It receives no security updates."
        ),
        recommendation=(
            "Rebuild this host from a supported, patched golden image (Windows 11 "
            "Enterprise multi-session or current Windows Server) and retire the old VM."
        ),
    ))


def _image_consistency(pool, t, findings):
    """Mixed OS builds in one pool = image drift; users get inconsistent behaviour."""
    builds = Counter(h.os_version for h in pool.hosts if h.os_version)
    if len(builds) <= t["max_os_builds_per_pool"] or not builds:
        return
    newest = latest_version(builds)
    stale = [h.name for h in pool.hosts if h.os_version and h.os_version != newest]
    findings.append(Finding(
        platform="AVD", resource=pool.name,
        severity=Severity.WARNING,
        category=Category.CONFIGURATION,
        title="Mixed OS builds in host pool",
        detail=(
            f"Pool '{pool.name}' runs {len(builds)} different OS builds: "
            + ", ".join(f"{v} ({c}x)" for v, c in builds.most_common())
            + f". Hosts behind newest ({newest}): " + summarize_names(stale)
        ),
        recommendation=(
            "Reimage all hosts from a single current golden image so users get "
            "consistent behaviour and patch level. Pooled host pools should be "
            "treated as cattle — replace, don't patch in place."
        ),
    ))
