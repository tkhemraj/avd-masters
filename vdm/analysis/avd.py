"""Best-practice analysis for Azure Virtual Desktop."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from ..models.metrics import AVDSnapshot, HealthStatus
from .base import Category, Finding, Severity

# Tunable thresholds — can be overridden via config["analysis"]["avd"]
_DEFAULTS = {
    "min_hosts_per_pool":          2,      # HA: minimum session hosts per pool
    "session_fill_warn_pct":      80.0,    # warn when host is >80% full
    "cpu_warn_pct":               75.0,
    "cpu_crit_pct":               90.0,
    "mem_warn_pct":               85.0,
    "mem_crit_pct":               95.0,
    "max_agent_versions_per_pool": 1,      # all hosts should run same agent
    "min_headroom_hosts":          1,      # pool must have ≥N available hosts
    "heartbeat_stale_minutes":    15,      # host is stale if no heartbeat in Nm
}


def analyse(snap: AVDSnapshot, cfg: Optional[dict] = None) -> list[Finding]:
    t = {**_DEFAULTS, **(cfg or {})}
    findings: list[Finding] = []

    for pool in snap.host_pools:
        _pool_availability(pool, t, findings)
        _pool_session_distribution(pool, t, findings)
        _agent_version_currency(pool, t, findings)
        for host in pool.hosts:
            _host_resources(pool.name, host, t, findings)
            _host_accepting_sessions(pool.name, host, findings)

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
    latest = max(versions, key=lambda v: v)

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
    ]
    for value, label, warn, crit in checks:
        if value is None:
            continue
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
                recommendation=(
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
