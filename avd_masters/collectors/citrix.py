"""Citrix Virtual Apps and Desktops (CVAD) collector.

Uses the Citrix Director OData REST API (no SDK dependency).
Alternatively, can use the Broker PowerShell SDK via WinRM.

Config keys:
  site_name          (display name, default "Citrix Site")
  director_url       (e.g. https://citrix-director.corp.local/Director)
  username           (domain\\user or user@domain)
  password
  domain             (optional — required for basic auth)
  verify_ssl         (default true)
  use_winrm          (default false — use WinRM+PowerShell instead of OData)
  winrm_host         (delivery controller hostname, required if use_winrm=true)
  winrm_username
  winrm_password
  winrm_transport    (default ntlm)
  poll_interval_s    (default 60)

Director OData endpoint: /Director/OData/v3/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin

from ..models.metrics import (
    CitrixController,
    CitrixDeliveryGroup,
    CitrixMachine,
    CitrixSnapshot,
    HealthStatus,
    ResourceMetrics,
    SessionState,
    UserSession,
)
from .base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)


def _map_reg_state(state: Optional[str]) -> HealthStatus:
    mapping = {
        "Registered": HealthStatus.OK,
        "Unregistered": HealthStatus.CRITICAL,
        "Unknown": HealthStatus.UNKNOWN,
    }
    return mapping.get(state or "", HealthStatus.UNKNOWN)


def _map_session_state(state: Optional[str]) -> SessionState:
    mapping = {
        "Connected": SessionState.ACTIVE,
        "Active": SessionState.ACTIVE,
        "Disconnected": SessionState.DISCONNECTED,
        "Reconnecting": SessionState.PENDING,
        "Terminating": SessionState.DISCONNECTED,
    }
    return mapping.get(state or "", SessionState.IDLE)


class CitrixODataCollector(BaseCollector):
    """Collector using Citrix Director OData v3 API."""

    name = "citrix"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._session = None

    def _get_session(self):
        try:
            import requests
            from requests.auth import HTTPDigestAuth
        except ImportError as exc:
            raise CollectorError(
                "requests library not installed. Run: pip install requests"
            ) from exc

        if self._session is not None:
            return self._session

        import requests

        s = requests.Session()
        s.verify = self.config.get("verify_ssl", True)

        username = self.config.get("username", "")
        password = self.config.get("password", "")
        director_url = self.config["director_url"].rstrip("/")

        # Citrix Director uses ASP.NET forms auth; try basic/NTLM
        transport = self.config.get("auth_transport", "basic")
        if transport == "ntlm":
            try:
                from requests_ntlm import HttpNtlmAuth
                s.auth = HttpNtlmAuth(username, password)
            except ImportError as exc:
                raise CollectorError(
                    "requests-ntlm not installed. Run: pip install requests-ntlm"
                ) from exc
        else:
            s.auth = (username, password)

        # Establish session / get CSRF token
        try:
            resp = s.get(f"{director_url}/", timeout=10)
            resp.raise_for_status()
        except Exception as exc:
            self.logger.debug("Director pre-auth request failed: %s", exc)

        self._session = s
        self._director_url = director_url
        return s

    def _odata_get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        session = self._get_session()
        url = f"{self._director_url}/OData/v3/{endpoint.lstrip('/')}"
        try:
            resp = session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            self.logger.error("OData request failed [%s]: %s", endpoint, exc)
            return None

    def _collect_delivery_groups(self) -> list[CitrixDeliveryGroup]:
        data = self._odata_get("DeliveryGroups")
        if not data:
            return []

        groups: list[CitrixDeliveryGroup] = []
        for item in data.get("value", []):
            dg = CitrixDeliveryGroup(
                name=item.get("Name") or "Unknown",
                description=item.get("Description"),
                enabled=item.get("Enabled", True),
                in_maintenance=item.get("InMaintenanceMode", False),
                total_machines=item.get("TotalMachines", 0),
                registered_machines=item.get("RegisteredMachines", 0),
                sessions_active=item.get("Sessions", 0),
                sessions_disconnected=item.get("DisconnectedSessions", 0),
            )
            groups.append(dg)
        return groups

    def _collect_machines(self) -> list[CitrixMachine]:
        data = self._odata_get(
            "Machines",
            params={"$select": "Name,DeliveryGroup,CatalogName,RegistrationState,"
                               "PowerState,InMaintenanceMode,SessionCount,FaultState,"
                               "AgentVersion,OSType"},
        )
        if not data:
            return []

        machines: list[CitrixMachine] = []
        for item in data.get("value", []):
            m = CitrixMachine(
                name=item.get("Name") or "Unknown",
                delivery_group=item.get("DeliveryGroup") or "",
                catalog=item.get("CatalogName") or "",
                registration_state=item.get("RegistrationState") or "Unknown",
                power_state=item.get("PowerState") or "Unknown",
                maintenance_mode=item.get("InMaintenanceMode", False),
                sessions=item.get("SessionCount", 0),
                agent_version=item.get("AgentVersion"),
                os_type=item.get("OSType"),
                fault_state=item.get("FaultState"),
            )
            machines.append(m)
        return machines

    def _collect_sessions(self) -> list[UserSession]:
        data = self._odata_get(
            "Sessions",
            params={"$select": "UserName,MachineName,SessionState,LogOnTime,IdleTime"},
        )
        if not data:
            return []

        sessions: list[UserSession] = []
        for item in data.get("value", []):
            sessions.append(
                UserSession(
                    username=item.get("UserName") or "unknown",
                    state=_map_session_state(item.get("SessionState")),
                    host=item.get("MachineName"),
                    idle_minutes=item.get("IdleTime"),
                )
            )
        return sessions

    def _collect_controllers(self) -> list[CitrixController]:
        data = self._odata_get("Controllers")
        if not data:
            return []

        controllers: list[CitrixController] = []
        for item in data.get("value", []):
            controllers.append(
                CitrixController(
                    name=item.get("DnsName") or item.get("Name") or "Unknown",
                    state=item.get("State") or "Unknown",
                    version=item.get("ControllerVersion"),
                )
            )
        return controllers

    def collect(self) -> CitrixSnapshot:
        site_name = self.config.get("site_name", "Citrix Site")

        snapshot = CitrixSnapshot(
            collected_at=datetime.now(timezone.utc),
            site_name=site_name,
        )

        try:
            snapshot.delivery_groups = self._collect_delivery_groups()
        except Exception as exc:
            snapshot.errors.append(f"Delivery groups: {exc}")

        try:
            machines = self._collect_machines()
            # Attach machines to their delivery groups
            dg_map = {g.name: g for g in snapshot.delivery_groups}
            for machine in machines:
                dg = dg_map.get(machine.delivery_group)
                if dg:
                    dg.machines.append(machine)
        except Exception as exc:
            snapshot.errors.append(f"Machines: {exc}")

        try:
            snapshot.user_sessions = self._collect_sessions()
        except Exception as exc:
            snapshot.errors.append(f"Sessions: {exc}")

        try:
            snapshot.controllers = self._collect_controllers()
        except Exception as exc:
            snapshot.errors.append(f"Controllers: {exc}")

        return snapshot


class CitrixWinRMCollector(BaseCollector):
    """Fallback collector using PowerShell via WinRM when no Director API is available."""

    name = "citrix"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)

    def _make_session(self, hostname: str):
        try:
            import winrm
        except ImportError as exc:
            raise CollectorError("pywinrm not installed. Run: pip install pywinrm") from exc

        transport = self.config.get("winrm_transport", "ntlm")
        port = self.config.get("winrm_port", 5985)
        return winrm.Session(
            f"http://{hostname}:{port}/wsman",
            auth=(self.config["winrm_username"], self.config["winrm_password"]),
            transport=transport,
        )

    def _run_ps(self, hostname: str, script: str) -> tuple[str, int]:
        import winrm
        session = self._make_session(hostname)
        result = session.run_ps(script)
        return result.std_out.decode("utf-8", errors="replace").strip(), result.status_code

    def collect(self) -> CitrixSnapshot:
        import json

        site_name = self.config.get("site_name", "Citrix Site")
        controller = self.config["winrm_host"]

        snapshot = CitrixSnapshot(
            collected_at=datetime.now(timezone.utc),
            site_name=site_name,
        )

        try:
            ps = (
                "Add-PSSnapin Citrix.* -ErrorAction SilentlyContinue; "
                "Get-BrokerDeliveryGroup | Select-Object Name,Enabled,InMaintenanceMode,"
                "TotalMachines,RegisteredMachines,Sessions,DisconnectedSessions | "
                "ConvertTo-Json -Compress"
            )
            stdout, rc = self._run_ps(controller, ps)
            if rc == 0 and stdout:
                raw = json.loads(stdout)
                if isinstance(raw, dict):
                    raw = [raw]
                for item in raw:
                    snapshot.delivery_groups.append(
                        CitrixDeliveryGroup(
                            name=item.get("Name") or "Unknown",
                            enabled=item.get("Enabled", True),
                            in_maintenance=item.get("InMaintenanceMode", False),
                            total_machines=item.get("TotalMachines", 0),
                            registered_machines=item.get("RegisteredMachines", 0),
                            sessions_active=item.get("Sessions", 0),
                            sessions_disconnected=item.get("DisconnectedSessions", 0),
                        )
                    )
        except Exception as exc:
            snapshot.errors.append(f"Delivery groups (WinRM): {exc}")

        try:
            ps = (
                "Add-PSSnapin Citrix.* -ErrorAction SilentlyContinue; "
                "Get-BrokerController | Select-Object DNSName,State,Version | "
                "ConvertTo-Json -Compress"
            )
            stdout, rc = self._run_ps(controller, ps)
            if rc == 0 and stdout:
                raw = json.loads(stdout)
                if isinstance(raw, dict):
                    raw = [raw]
                for item in raw:
                    snapshot.controllers.append(
                        CitrixController(
                            name=item.get("DNSName") or "Unknown",
                            state=item.get("State") or "Unknown",
                            version=item.get("Version"),
                        )
                    )
        except Exception as exc:
            snapshot.errors.append(f"Controllers (WinRM): {exc}")

        return snapshot


def make_citrix_collector(config: dict[str, Any]) -> BaseCollector:
    """Factory — returns OData or WinRM collector based on config."""
    if config.get("use_winrm", False):
        return CitrixWinRMCollector(config)
    return CitrixODataCollector(config)
