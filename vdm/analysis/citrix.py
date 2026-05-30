"""Best-practice analysis for Citrix Virtual Apps and Desktops (CVAD)."""

from __future__ import annotations

from collections import Counter
from typing import Optional

from ..models.metrics import CitrixSnapshot, HealthStatus
from .base import Category, Finding, Severity

_DEFAULTS = {
    "min_controllers":             2,     # HA: at least 2 Delivery Controllers
    "min_vdas_per_group":          2,     # HA: at least 2 registered VDAs per DG
    "capacity_headroom_pct":      25.0,   # registered VDAs should exceed peak sessions by ≥25%
    "max_unregistered_pct":       10.0,   # warn if >10% of VDAs in a DG are unregistered
    "max_agent_versions_per_dg":   1,     # all VDAs in a DG should run same agent
    "maintenance_mode_warn":      True,   # warn on delivery groups left in maintenance
    "session_per_vda_warn":       8,      # warn if avg sessions per registered VDA exceeds this
    "session_per_vda_crit":       12,     # critical threshold for sessions per VDA
}


def analyse(snap: CitrixSnapshot, cfg: Optional[dict] = None) -> list[Finding]:
    t = {**_DEFAULTS, **(cfg or {})}
    findings: list[Finding] = []

    _controller_redundancy(snap, t, findings)
    for dg in snap.delivery_groups:
        _dg_availability(snap.site_name, dg, t, findings)
        _dg_capacity(snap.site_name, dg, t, findings)
        _dg_vda_currency(snap.site_name, dg, t, findings)
        _dg_maintenance(snap.site_name, dg, t, findings)
        _dg_session_density(snap.site_name, dg, t, findings)

    return findings


def _controller_redundancy(snap, t, findings):
    total = len(snap.controllers)
    active = sum(1 for c in snap.controllers if c.status == HealthStatus.OK)
    minimum = t["min_controllers"]

    if total < minimum:
        findings.append(Finding(
            platform="Citrix", resource=snap.site_name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="Insufficient Delivery Controllers for HA",
            detail=(
                f"Site '{snap.site_name}' has {total} controller(s), "
                f"minimum recommended is {minimum}. "
                "A single controller failure will prevent VDA registrations "
                "and new session launches site-wide."
            ),
            recommendation=(
                "Install and configure a second Delivery Controller. "
                "Citrix best practice requires a minimum of 2 controllers per zone. "
                "For large sites (>1000 VDAs) consider 3–4 controllers per zone."
            ),
        ))
    elif active < total:
        down = [c.name for c in snap.controllers if c.status != HealthStatus.OK]
        findings.append(Finding(
            platform="Citrix", resource=snap.site_name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="One or more Delivery Controllers not active",
            detail=f"Controllers not in Active state: {', '.join(down)}",
            recommendation=(
                "Check the Citrix Broker Service on the affected controller(s). "
                "Review the System log and Citrix-related event logs. "
                "Verify SQL Server connectivity from each controller."
            ),
        ))
    else:
        findings.append(Finding(
            platform="Citrix", resource=snap.site_name,
            severity=Severity.PASS,
            category=Category.AVAILABILITY,
            title="Delivery Controllers redundant and active",
            detail=f"All {active} controller(s) in site '{snap.site_name}' are active.",
            recommendation="",
        ))


def _dg_availability(site, dg, t, findings):
    registered = dg.registered_machines
    total = dg.total_machines
    minimum = t["min_vdas_per_group"]

    if registered == 0 and total > 0:
        findings.append(Finding(
            platform="Citrix", resource=dg.name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="Delivery group has zero registered VDAs",
            detail=(
                f"'{dg.name}' has {total} VDA(s) but none are registered "
                "with the Delivery Controller. No sessions can be brokered."
            ),
            recommendation=(
                "Check VDA connectivity to the Delivery Controllers. "
                "On each VDA run: Get-BrokerDesktop | where RegistrationState -ne Registered "
                "— look for FaultState and SummaryState for root cause. "
                "Common causes: controller unreachable, VDA cert mismatch, or machine policy not applied."
            ),
        ))
    elif registered < minimum:
        findings.append(Finding(
            platform="Citrix", resource=dg.name,
            severity=Severity.CRITICAL,
            category=Category.AVAILABILITY,
            title="Delivery group below minimum VDA count for HA",
            detail=(
                f"'{dg.name}' has {registered} registered VDA(s), "
                f"minimum recommended is {minimum} for redundancy. "
            ),
            recommendation=(
                f"Add at least {minimum - registered} more VDA(s) to '{dg.name}'. "
                "Provision additional machines in the machine catalog and add them to the group."
            ),
        ))
    elif total > 0:
        unregistered = total - registered
        unregistered_pct = (unregistered / total) * 100
        max_unregistered = t["max_unregistered_pct"]

        if unregistered_pct > max_unregistered:
            findings.append(Finding(
                platform="Citrix", resource=dg.name,
                severity=Severity.WARNING,
                category=Category.AVAILABILITY,
                title="Elevated unregistered VDA count",
                detail=(
                    f"{unregistered} of {total} VDAs ({unregistered_pct:.1f}%) are unregistered "
                    f"in delivery group '{dg.name}' (threshold: {max_unregistered:.0f}%)."
                ),
                recommendation=(
                    "Investigate unregistered VDAs using Citrix Director or Studio. "
                    "Check power state, VDA service status (BrokerAgent), "
                    "and Citrix-related event logs on each unregistered machine."
                ),
            ))
        else:
            findings.append(Finding(
                platform="Citrix", resource=dg.name,
                severity=Severity.PASS,
                category=Category.AVAILABILITY,
                title="VDA registration healthy",
                detail=(
                    f"'{dg.name}': {registered}/{total} VDAs registered "
                    f"({(registered / total * 100):.1f}%)."
                ),
                recommendation="",
            ))


def _dg_capacity(site, dg, t, findings):
    if dg.registered_machines == 0:
        return

    headroom_needed = t["capacity_headroom_pct"] / 100
    active = dg.sessions_active
    vdas = dg.registered_machines

    # Check if registered VDA count provides headroom above current session load
    if active > 0:
        required_vdas = active * (1 + headroom_needed)
        if vdas < required_vdas:
            shortage = int(required_vdas - vdas)
            findings.append(Finding(
                platform="Citrix", resource=dg.name,
                severity=Severity.WARNING,
                category=Category.CAPACITY,
                title="Delivery group lacks capacity headroom",
                detail=(
                    f"'{dg.name}' has {active} active sessions across {vdas} registered VDA(s). "
                    f"At current load, {t['capacity_headroom_pct']:.0f}% headroom requires "
                    f"≥{int(required_vdas)} VDAs; {shortage} more needed."
                ),
                recommendation=(
                    "Provision additional VDAs in the machine catalog, or configure "
                    "Citrix Autoscale to add capacity automatically at peak load. "
                    "Review the delivery group's power management schedule."
                ),
            ))


def _dg_vda_currency(site, dg, t, findings):
    if not dg.machines:
        return

    versions = Counter(
        m.agent_version for m in dg.machines if m.agent_version
    )
    if not versions or len(versions) <= t["max_agent_versions_per_dg"]:
        if versions:
            latest = max(versions)
            findings.append(Finding(
                platform="Citrix", resource=dg.name,
                severity=Severity.PASS,
                category=Category.CURRENCY,
                title="All VDAs on consistent agent version",
                detail=f"All VDAs in '{dg.name}' are on VDA version {latest}.",
                recommendation="",
            ))
        return

    latest = max(versions)
    stale = [m.name for m in dg.machines
             if m.agent_version and m.agent_version != latest]

    findings.append(Finding(
        platform="Citrix", resource=dg.name,
        severity=Severity.WARNING,
        category=Category.CURRENCY,
        title="Mixed VDA agent versions in delivery group",
        detail=(
            f"'{dg.name}' has {len(versions)} different VDA versions: "
            + ", ".join(f"{v} ({c}x)" for v, c in versions.most_common())
            + f". Not on latest ({latest}): "
            + ", ".join(stale[:5])
            + ("…" if len(stale) > 5 else "")
        ),
        recommendation=(
            "Update all VDAs to the same version using MCS/PVS image updates "
            "or an in-place VDA upgrade during a maintenance window. "
            "Mixed versions can cause unexpected behaviour with certain Citrix policies."
        ),
    ))


def _dg_maintenance(site, dg, t, findings):
    if not t["maintenance_mode_warn"]:
        return
    if dg.in_maintenance:
        findings.append(Finding(
            platform="Citrix", resource=dg.name,
            severity=Severity.WARNING,
            category=Category.CONFIGURATION,
            title="Delivery group is in maintenance mode",
            detail=(
                f"'{dg.name}' has maintenance mode enabled. "
                "No new sessions can be brokered to this group. "
                "This is expected during planned maintenance but is often forgotten."
            ),
            recommendation=(
                "If maintenance is complete, disable maintenance mode in Citrix Studio: "
                "Delivery Groups > right-click > Turn Off Maintenance Mode. "
                "Or via PowerShell: Set-BrokerDesktopGroup -Name '{dg.name}' "
                "-InMaintenanceMode $false"
            ),
        ))


def _dg_session_density(site, dg, t, findings):
    if dg.registered_machines == 0 or dg.sessions_active == 0:
        return

    avg = dg.sessions_active / dg.registered_machines
    warn = t["session_per_vda_warn"]
    crit = t["session_per_vda_crit"]

    if avg >= crit:
        findings.append(Finding(
            platform="Citrix", resource=dg.name,
            severity=Severity.CRITICAL,
            category=Category.PERFORMANCE,
            title="Session density critically high",
            detail=(
                f"'{dg.name}' averages {avg:.1f} active sessions per registered VDA "
                f"(critical threshold: {crit}). "
                "Users will experience severe performance degradation."
            ),
            recommendation=(
                "Scale out immediately: provision more VDAs or power on additional machines. "
                "Review Autoscale thresholds to ensure capacity is added earlier."
            ),
        ))
    elif avg >= warn:
        findings.append(Finding(
            platform="Citrix", resource=dg.name,
            severity=Severity.WARNING,
            category=Category.PERFORMANCE,
            title="Session density elevated",
            detail=(
                f"'{dg.name}' averages {avg:.1f} active sessions per VDA "
                f"(warning threshold: {warn}). "
                "Monitor for user-reported performance issues."
            ),
            recommendation=(
                "Review Autoscale or power management policy to bring more VDAs online. "
                "Consider adjusting the session load index or concurrency limits."
            ),
        ))
    else:
        findings.append(Finding(
            platform="Citrix", resource=dg.name,
            severity=Severity.PASS,
            category=Category.PERFORMANCE,
            title="Session density within recommended range",
            detail=f"'{dg.name}': {avg:.1f} sessions/VDA (threshold: {warn}).",
            recommendation="",
        ))
