"""On-Premises Terminal Services / RDS collector.

Uses WinRM + WMI to query session hosts and the RD Broker.

Requires:
  - pywinrm

Config keys:
  farm_name          (display name, default "RDS Farm")
  hosts              (list of hostnames — all session hosts + brokers)
  broker_hosts       (list — subset of hosts that are RD Connection Brokers)
  license_server     (hostname of RD Licensing server, optional)
  winrm_username     (domain\\user or user@domain)
  winrm_password
  winrm_transport    (ntlm | kerberos | basic, default ntlm)
  winrm_port         (default 5985)
  use_ssl            (default false)
  poll_interval_s    (default 60)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ..models.metrics import (
    HealthStatus,
    RDSBroker,
    RDSHost,
    RDSLicenseInfo,
    RDSSnapshot,
    ResourceMetrics,
    SessionState,
    UserSession,
)
from .base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)

# WMI queries
_WMI_OS = (
    "SELECT Caption, LastBootUpTime FROM Win32_OperatingSystem"
)
_WMI_PERF_CPU = (
    "SELECT PercentProcessorTime FROM Win32_PerfFormattedData_PerfOS_Processor "
    "WHERE Name='_Total'"
)
_WMI_PERF_MEM = (
    "SELECT AvailableMBytes, TotalVisibleMemorySize FROM Win32_OperatingSystem"
)
_WMI_DISK = (
    "SELECT DeviceID, FreeSpace, Size FROM Win32_LogicalDisk WHERE DriveType=3"
)
_WMI_SESSIONS = (
    "SELECT SessionId, UserName, State, IdleTime, LogonTime "
    "FROM Win32_LogonSession WHERE LogonType=10"
)
_WMI_TS_SESSIONS = (
    "SELECT SessionName, UserName, State, SessionId "
    "FROM Win32_TerminalServiceSetting"
)

# PowerShell snippets run over WinRM
_PS_SESSIONS = (
    "Get-RDUserSession -ConnectionBroker {broker} | "
    "Select-Object UserName,HostServer,SessionState,IdleTime,LogonTime | "
    "ConvertTo-Json -Compress"
)
_PS_SERVER_INFO = (
    "Get-RDServer -ConnectionBroker {broker} -Role RDS-RD-SERVER | "
    "Select-Object Server,Roles | ConvertTo-Json -Compress"
)
_PS_LICENSE = (
    "$lic = Get-WmiObject -Class Win32_TSLicenseKeyPack; "
    "$lic | Select-Object TotalLicenses,IssuedLicenses,KeyPackType | ConvertTo-Json -Compress"
)


def _winrm_run(session, script: str) -> tuple[str, str, int]:
    """Execute a PowerShell script via WinRM and return (stdout, stderr, rc)."""
    result = session.run_ps(script)
    return (
        result.std_out.decode("utf-8", errors="replace").strip(),
        result.std_err.decode("utf-8", errors="replace").strip(),
        result.status_code,
    )


def _parse_uptime(last_boot_str: Optional[str]) -> Optional[float]:
    """Convert WMI datetime string to uptime hours."""
    if not last_boot_str:
        return None
    try:
        # WMI format: 20240101120000.000000+000
        dt_str = last_boot_str[:14]
        boot = datetime.strptime(dt_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - boot
        return round(delta.total_seconds() / 3600, 1)
    except Exception:
        return None


class RDSCollector(BaseCollector):
    name = "rds"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._sessions_cache: dict[str, Any] = {}

    def _make_session(self, hostname: str):
        try:
            import winrm
        except ImportError as exc:
            raise CollectorError(
                "pywinrm not installed. Run: pip install pywinrm"
            ) from exc

        transport = self.config.get("winrm_transport", "ntlm")
        port = self.config.get("winrm_port", 5985)
        use_ssl = self.config.get("use_ssl", False)
        scheme = "https" if use_ssl else "http"

        return winrm.Session(
            f"{scheme}://{hostname}:{port}/wsman",
            auth=(self.config["winrm_username"], self.config["winrm_password"]),
            transport=transport,
        )

    def _collect_host_metrics(self, hostname: str) -> tuple[HealthStatus, ResourceMetrics, Optional[float]]:
        """Query a single session host over WinRM."""
        import json

        metrics = ResourceMetrics()
        uptime_hours = None

        try:
            session = self._make_session(hostname)

            # CPU
            cpu_ps = (
                "(Get-WmiObject Win32_PerfFormattedData_PerfOS_Processor "
                "-Filter \"Name='_Total'\").PercentProcessorTime"
            )
            stdout, _, rc = _winrm_run(session, cpu_ps)
            if rc == 0 and stdout:
                metrics.cpu_percent = float(stdout.strip())

            # Memory
            mem_ps = (
                "$os=Get-WmiObject Win32_OperatingSystem; "
                "[math]::Round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) "
                "/ $os.TotalVisibleMemorySize * 100, 1)"
            )
            stdout, _, rc = _winrm_run(session, mem_ps)
            if rc == 0 and stdout:
                metrics.memory_percent = float(stdout.strip())

            # Disk (C: drive)
            disk_ps = (
                "$d=Get-WmiObject Win32_LogicalDisk -Filter \"DeviceID='C:'\"; "
                "[math]::Round(($d.Size - $d.FreeSpace) / $d.Size * 100, 1)"
            )
            stdout, _, rc = _winrm_run(session, disk_ps)
            if rc == 0 and stdout:
                metrics.disk_percent = float(stdout.strip())

            # Uptime
            uptime_ps = (
                "$boot=(Get-WmiObject Win32_OperatingSystem).LastBootUpTime; "
                "$boot"
            )
            stdout, _, rc = _winrm_run(session, uptime_ps)
            if rc == 0 and stdout:
                uptime_hours = _parse_uptime(stdout.strip())

            # Status: critical thresholds
            status = HealthStatus.OK
            if metrics.cpu_percent is not None and metrics.cpu_percent > 90:
                status = HealthStatus.CRITICAL
            elif metrics.cpu_percent is not None and metrics.cpu_percent > 75:
                status = HealthStatus.WARNING
            if metrics.memory_percent is not None and metrics.memory_percent > 95:
                status = HealthStatus.CRITICAL
            elif metrics.memory_percent is not None and metrics.memory_percent > 85:
                status = max(status, HealthStatus.WARNING)  # type: ignore[assignment]
            if metrics.disk_percent is not None and metrics.disk_percent > 95:
                status = HealthStatus.CRITICAL

            return status, metrics, uptime_hours

        except Exception as exc:
            self.logger.warning("Cannot reach host %s: %s", hostname, exc)
            return HealthStatus.OFFLINE, metrics, None

    def _collect_sessions(self, broker: str) -> list[UserSession]:
        """Pull user sessions from the RD Connection Broker via PowerShell."""
        import json

        sessions: list[UserSession] = []
        try:
            session = self._make_session(broker)
            ps = (
                "Get-RDUserSession -ConnectionBroker localhost | "
                "Select-Object UserName,HostServer,SessionState,IdleTime,LogonTime | "
                "ConvertTo-Json -Compress"
            )
            stdout, stderr, rc = _winrm_run(session, ps)
            if rc != 0 or not stdout:
                self.logger.warning("Get-RDUserSession failed on %s: %s", broker, stderr)
                return sessions

            raw = json.loads(stdout)
            if isinstance(raw, dict):
                raw = [raw]

            for s in raw:
                state_str = (s.get("SessionState") or "").lower()
                if "active" in state_str:
                    state = SessionState.ACTIVE
                elif "disconnect" in state_str:
                    state = SessionState.DISCONNECTED
                else:
                    state = SessionState.IDLE

                sessions.append(
                    UserSession(
                        username=s.get("UserName") or "unknown",
                        state=state,
                        host=s.get("HostServer"),
                        idle_minutes=s.get("IdleTime"),
                    )
                )
        except Exception as exc:
            self.logger.warning("Failed to collect sessions from broker %s: %s", broker, exc)

        return sessions

    def _collect_license(self, license_server: str) -> Optional[RDSLicenseInfo]:
        import json

        try:
            session = self._make_session(license_server)
            stdout, _, rc = _winrm_run(session, _PS_LICENSE)
            if rc != 0 or not stdout:
                return None
            raw = json.loads(stdout)
            if isinstance(raw, dict):
                raw = [raw]

            total = sum(int(r.get("TotalLicenses", 0)) for r in raw)
            issued = sum(int(r.get("IssuedLicenses", 0)) for r in raw)
            return RDSLicenseInfo(
                server=license_server,
                total_cals=total,
                used_cals=issued,
                available_cals=total - issued,
            )
        except Exception as exc:
            self.logger.warning("Failed to collect license info from %s: %s", license_server, exc)
            return None

    def collect(self) -> RDSSnapshot:
        farm_name = self.config.get("farm_name", "RDS Farm")
        all_hosts: list[str] = self.config.get("hosts", [])
        broker_hosts: list[str] = self.config.get("broker_hosts", [])
        license_server: Optional[str] = self.config.get("license_server")

        if not all_hosts:
            raise CollectorError("No hosts configured for RDS collector")

        snapshot = RDSSnapshot(
            collected_at=datetime.now(timezone.utc),
            farm_name=farm_name,
        )

        for hostname in all_hosts:
            if hostname in broker_hosts:
                try:
                    session = self._make_session(hostname)
                    stdout, _, rc = _winrm_run(session, "hostname")
                    status = HealthStatus.OK if rc == 0 else HealthStatus.CRITICAL
                except Exception:
                    status = HealthStatus.CRITICAL

                snapshot.brokers.append(
                    RDSBroker(
                        hostname=hostname,
                        status=status,
                        is_active=(status == HealthStatus.OK),
                    )
                )
            else:
                status, metrics, uptime = self._collect_host_metrics(hostname)
                snapshot.session_hosts.append(
                    RDSHost(
                        hostname=hostname,
                        status=status,
                        metrics=metrics,
                        uptime_hours=uptime,
                    )
                )

        # Collect sessions from the first available broker
        for broker in broker_hosts:
            sessions = self._collect_sessions(broker)
            if sessions:
                snapshot.user_sessions = sessions
                # Back-fill per-host session counts
                for s in sessions:
                    if s.host:
                        for h in snapshot.session_hosts:
                            if h.hostname.lower() == s.host.lower():
                                if s.state == SessionState.ACTIVE:
                                    h.active_sessions += 1
                                elif s.state == SessionState.DISCONNECTED:
                                    h.disconnected_sessions += 1
                break

        if license_server:
            snapshot.license_info = self._collect_license(license_server)

        return snapshot
