# VirtualDesktopMasters

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-tkhemraj.github.io%2Favd--masters-blue?style=flat-square)](https://tkhemraj.github.io/avd-masters)
[![Prometheus](https://img.shields.io/badge/exporter-prometheus-orange?style=flat-square)](https://prometheus.io)

Unified monitoring for **Azure Virtual Desktop**, **RDS Terminal Services**, and **Citrix VDI** from a single Python process. Covers the full observability stack: live TUI dashboard, Prometheus exporter, Grafana dashboards, Alertmanager with MS Teams delivery, scored best-practice analysis, and GPU/vGPU slice ROI monitoring via `nvidia-smi` over WinRM.

> **Module naming**: The Python module (`avd_masters`) and Prometheus metric prefix (`avd_masters_`) are CI pipeline names pending rename to `vdm` in an upcoming release. Existing dashboards and alert rules will continue to function through the transition.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      VirtualDesktopMasters                      │
│                                                                 │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │ AVD Collector│  │  RDS Collector   │  │ Citrix Collector │  │
│  │ Azure SDK /  │  │ WinRM · WMI ·    │  │ Director OData / │  │
│  │ Azure Monitor│  │ PowerShell       │  │ WinRM fallback   │  │
│  └──────┬───────┘  └───────┬──────────┘  └────────┬─────────┘  │
│         └──────────────────┴─────────────────────-┘            │
│                        GPU Collector                            │
│             nvidia-smi vgpu · WMI GPUEngine · top-N            │
│                        ↓ MasterSnapshot                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Monitoring Engine                       │  │
│  │       threshold evaluation · alert state machine         │  │
│  └──────┬──────────────────┬────────────────────┬───────────┘  │
│         │                  │                    │               │
│    Rich TUI           Prometheus           Teams / Console      │
│    dashboard          /metrics             notifiers            │
│                            ↓                                    │
│                    Alertmanager                                  │
│                    (29 rules · Teams cards)                     │
└─────────────────────────────────────────────────────────────────┘
```

All platform collectors run concurrently on a configurable poll interval. The engine evaluates thresholds, fires notifier callbacks only on state transitions (not every poll), and updates Prometheus gauges atomically after each collection pass.

---

## Platform collectors

### Azure Virtual Desktop

Uses `DefaultAzureCredential` — supports service principal (env vars), managed identity, workload identity, and `az login`. Queries the Desktop Virtualisation management plane for host pool and session host state, then supplements with Azure Monitor VM metrics (CPU, memory) for NV-series GPU hosts.

**Required SDK packages:** `azure-identity`, `azure-mgmt-desktopvirtualization`, `azure-mgmt-monitor`, `azure-mgmt-compute`

Collected per scrape:
- Host pool: load balancer type, active/disconnected session counts, available host count
- Session host: status (AVD agent health string → 0–4 encoding), session count, allow_new_sessions, agent version, last heartbeat, VM-level CPU/memory from Azure Monitor
- User sessions: UPN, session state, host assignment

### RDS Terminal Services

WinRM over HTTPS (port 5986, NTLM by default). No agent required — queries via `Get-CimInstance` (Win32_PerfFormattedData, Win32_LogicalDisk, Win32_OperatingSystem) and `Get-RDUserSession` on the RD Connection Broker.

**WinRM prerequisites on each target host:**
```powershell
Enable-PSRemoting -Force
Set-Item WSMan:\localhost\Service\Auth\Negotiate -Value $true
New-SelfSignedCertificate -DnsName $env:COMPUTERNAME -CertStoreLocation Cert:\LocalMachine\My
```

The service account requires membership in the local **Remote Management Users** group and **Remote Desktop Users** on each RDSH. For `Get-RDUserSession`, it must have the **RD Management Server** role or equivalent RSAT permissions on the broker.

Collected per scrape:
- Session host: CPU%, memory%, C: disk%, uptime hours, active/disconnected session counts
- RD Connection Broker: WinRM reachability → OK/CRITICAL
- RD Licensing: total CALs, issued CALs, utilisation %, status threshold evaluation
- User sessions: username, host, state, idle time

### Citrix VDI (CVAD)

Primary path uses the Director OData v3 REST API (`/Director/OData/v3/`). Supports NTLM (requires `requests-ntlm`) and basic auth (TLS required). Session is persisted and re-authenticated automatically on 401/403. Fallback path uses WinRM + `Get-BrokerDeliveryGroup` / `Get-BrokerController` for environments without Director.

Collected per scrape:
- Delivery groups: enabled state, maintenance mode, total/registered VDA counts, active/disconnected session counts
- Machines (OData path): registration state, power state, fault state, agent version, session count
- Delivery Controllers: DNS name, state (Active/On/Off/Failed)
- User sessions: username, machine name, session state, idle time

### GPU / vGPU

Runs against any host with WinRM access. Two collection layers:

1. **WMI** (all GPU vendors): `Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine` and `GPUAdapterMemory` — engine utilisation per engine type (3D, Compute, Copy, VideoEncode, VideoDecode) and per PID for top-N process attribution
2. **nvidia-smi** (NVIDIA only): physical GPU stats (`--query-gpu`) and per-vGPU instance metrics (`vgpu --query-vgpu`) — SM utilisation, frame buffer used/total, encoder/decoder utilisation, VM name, GPU UUID

vGPU profile names are parsed from NVIDIA's `GRID {GPU}-{memory_gb}{type}` convention. Profile type `B` (GRID vPC), `Q` (Quadro vDWS), `C` (vCS), `A` (vApps) determines licence tier and ROI analysis thresholds.

---

## Installation

```bash
git clone https://github.com/tkhemraj/avd-masters.git
cd avd-masters
pip install -r requirements.txt

# Optional: NTLM for Citrix Director
pip install requests-ntlm

# Optional: Prometheus exporter
pip install prometheus_client
```

---

## Configuration

```bash
cp config/config.yaml.example config.yaml
chmod 600 config.yaml
```

All string values support `${ENV_VAR}` substitution — the process refuses to start if a referenced variable is unset. Credentials should never be written directly into `config.yaml`; use environment variables or a secrets manager that injects them at runtime.

On startup, the config loader checks file permissions and logs a warning if `config.yaml` is group- or world-readable.

**Minimal multi-platform config:**

```yaml
rds:
  farm_name: "Production RDS Farm"
  hosts: [rdsh01.corp.local, rdsh02.corp.local, rdbroker01.corp.local]
  broker_hosts: [rdbroker01.corp.local]
  license_server: rdlicense01.corp.local
  winrm_username: "CORP\\svc-monitoring"
  winrm_password: "${RDS_PASSWORD}"
  winrm_transport: ntlm          # ntlm | kerberos — basic rejected without TLS
  winrm_port: 5986               # 5986 = HTTPS (default), 5985 = HTTP (warns)
  use_ssl: true

avd:
  subscription_id: "${AZURE_SUBSCRIPTION_ID}"
  # resource_groups: [rg-avd-prod]  # omit to scan all RGs

citrix:
  site_name: "Production Site"
  director_url: "https://citrix-director.corp.local/Director"
  username: "CORP\\svc-monitoring"
  password: "${CITRIX_PASSWORD}"
  auth_transport: ntlm
  verify_ssl: true

gpu:
  enabled: true
  collect_processes: true
  top_processes: 10

prometheus:
  port: 9090
  host: 127.0.0.1    # set 0.0.0.0 only if Prometheus scrapes from a remote host

notifiers:
  console: {}
  # teams:
  #   webhook_url: "${TEAMS_WEBHOOK_URL}"

poll_interval_s: 60
```

Full config reference: [tkhemraj.github.io/avd-masters/#reference](https://tkhemraj.github.io/avd-masters/#reference)

---

## Running

```bash
# Full TUI dashboard with live refresh
python -m avd_masters [--config PATH]

# Headless loop — runs collectors and fires notifiers, no TUI
python -m avd_masters --no-dashboard

# Prometheus exporter only — requires prometheus: block in config
python -m avd_masters --exporter-only

# Best-practice analysis — exit 0 (OK) or 2 (CRITICAL findings present)
python -m avd_masters --analyze [--show-passes]

# Single collection pass to stdout as JSON
python -m avd_masters --once | jq '.rds.license_info'

# Override log level
python -m avd_masters --log-level DEBUG
```

---

## Prometheus

**Scrape config:**

```yaml
scrape_configs:
  - job_name: vdm
    static_configs:
      - targets: ["monitoring-host:9090"]
    scrape_interval: 60s
    scrape_timeout: 30s

rule_files:
  - /etc/prometheus/alerts/avd_masters.yml
```

Copy `prometheus/alerts/avd_masters.yml` to your Prometheus server. 29 rules across four groups:

| Group | Rules | Notes |
|---|---|---|
| `avd_masters.avd` | 9 | Session host offline/critical/warning, CPU/memory, pool degraded |
| `avd_masters.rds` | 11 | Host offline, CPU/memory/disk, CAL critical (>95%) / warning (>80%), broker down |
| `avd_masters.citrix` | 6 | Controller down, major outage (>50% VDAs unregistered), delivery group down |
| `avd_masters.meta` | 3 | Stale data warning (>5m) / critical (>10m), high error rate |

All rules carry `severity` and `platform` labels. Duration tuning: 2m for offline/broker failures, 5m for resource criticals, 10m for warnings, 30m for licensing.

**Status gauge encoding** (all `*_status` metrics): `0=ok · 1=warning · 2=critical · 3=unknown · 4=offline`

Full metrics catalog: [tkhemraj.github.io/avd-masters/#metrics](https://tkhemraj.github.io/avd-masters/#metrics)

---

## Grafana

Import `grafana/avd_masters_dashboard.json` (Grafana 10+, Prometheus datasource).

25 panels across three platform rows plus a summary row. All status columns use value-mapped colour-background display (0→green, 1→yellow, 2→red). Table panels use instant queries with `merge` transform to show current state rather than time series.

To rebuild after modifying panel definitions:

```bash
python grafana/dashboard_gen.py > grafana/avd_masters_dashboard.json
```

---

## Alertmanager

Requires Alertmanager ≥ 0.27 for native `msteams_configs`. Configuration in `prometheus/alertmanager/alertmanager.yml`.

```bash
export TEAMS_WEBHOOK_CRITICAL="https://outlook.office.com/webhook/..."
export TEAMS_WEBHOOK_WARNING="https://outlook.office.com/webhook/..."
export TEAMS_WEBHOOK_META="https://outlook.office.com/webhook/..."
```

Routing: critical alerts (10s `group_wait`, 1h `repeat_interval`) → `teams-critical`; warnings (2m, 4h) → `teams-warning`; stale data and collection errors → `teams-meta`.

**Inhibition rules** prevent noise during outages:
- Stale data (`AVDMastersDataStaleCritical`) inhibits all per-host alerts for that platform
- `AVDHostPoolNoAvailableHosts` inhibits per-host `AVDSessionHostCritical` for the same pool
- `CitrixDeliveryGroupMajorOutage` inhibits individual unregistered-VDA warnings for the same group
- Critical resource alert inhibits the corresponding warning alert for the same resource

For Alertmanager < 0.27, use the `prometheus-msteams` proxy — configuration notes are in `prometheus/alertmanager/alertmanager.yml`.

---

## Best-practice analysis

```bash
python -m avd_masters --analyze
```

Scored report (critical −10pts, warning −3pts) per platform. Actionable findings only by default; `--show-passes` includes passing checks. Exit code 2 when any CRITICAL finding is present — suitable for CI gates and scheduled health checks.

Selected checks:

- **AVD**: host pool below N+1 redundancy, pool with zero available hosts, session fill >80%, mixed agent versions, BreadthFirst load skew >2.5×
- **RDS**: single Connection Broker, CAL utilisation >80%/95%, farm headroom <20%, disconnected session ratio >30%, host uptime >30 days (patch hygiene)
- **Citrix**: fewer than 2 Delivery Controllers, unregistered VDA ratio >10%, session density >8 per VDA, delivery group in maintenance mode
- **GPU**: saturated slice (FB >88% or SM >85% or encoder >80%), oversized/idle slice (FB <20%, SM <5%), Q-profile instances with SM <15% (licence waste), slice packing efficiency <30%

---

## GPU / vGPU analysis

The GPU layer runs on top of any WinRM-accessible Windows host. NVIDIA-specific data (per-slice FB, SM%, encoder/decoder%) requires the NVIDIA vGPU host driver and a valid vGPU licence on the hypervisor.

**Key findings the analyser surfaces:**

| Finding | Signal | Action |
|---|---|---|
| Saturated slice | FB >88%, SM >85%, or encoder >80% | Migrate VM to next larger profile |
| Encoder bottleneck | Encoder >80% | Direct user-visible lag in remoting session |
| Idle/oversized slice | FB <20%, SM <5% | Downsize profile — pack more users per pGPU |
| Q-profile on light workload | SM <15%, FB <40% on a Quadro vDWS instance | Downgrade to B-profile — 3–5× licence cost reduction |
| Low packing efficiency | Aggregate FB in use <30% of allocated across all slices | Use smaller profiles to increase GPU density |
| GPU process hog | Single PID >60% of a GPU engine | Apply vGPU equal-share scheduler or isolate workload |

**Prometheus vGPU metrics** are labelled by `vm_name`, `profile`, and `profile_type` — enabling Grafana panels and alerts to target specific slice types (e.g., alert when any Q-profile instance has SM <15% for >30m).

---

## Docker Compose

Full stack (exporter + Prometheus + Alertmanager):

```bash
cd prometheus
# Copy and edit config, set credential env vars, then:
docker compose up -d
```

The `avd-masters` service accepts Azure credentials via environment variables passed through from the host (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`). Platform passwords are injected via `${ENV_VAR}` substitution in the mounted `config.yaml`.

---

## Security notes

- WinRM defaults to port **5986 (HTTPS)**. Plain HTTP (`use_ssl: false`) logs a WARNING. `basic` transport without TLS raises `CollectorError` at startup — it is not silently downgraded.
- `${ENV_VAR}` substitution is resolved at load time. An unset variable exits the process with a clear error rather than passing an empty string to authentication.
- Exception messages are passed through `sanitize_error()` before appearing in logs, `snapshot.errors`, Teams notifications, or `--once` JSON output. The sanitiser redacts `user:pass@url` credential-in-URL patterns and `key=value` password patterns.
- The Prometheus `/metrics` endpoint binds to `127.0.0.1` by default. It is unauthenticated — protect with a firewall ACL or reverse proxy if remote scraping is needed.
- Config file permissions are checked on startup; a warning is logged if the file is group- or world-readable.
- Stack traces (`exc_info`) are emitted at DEBUG level only — not at ERROR — to prevent config dicts containing credentials from appearing in structured log aggregators.

---

## Project structure

```
avd_masters/
├── collectors/       avd.py  rds.py  citrix.py  gpu.py  base.py
├── models/           metrics.py  gpu.py
├── analysis/         avd.py  rds.py  citrix.py  gpu.py  report.py  base.py
├── dashboard/        tui.py  gpu_panel.py
├── exporters/        prometheus.py
├── notifiers/        console.py  teams.py  base.py
├── engine.py         collection orchestration, alert state machine
├── config.py         YAML loader, ${ENV_VAR} resolution, permission check
└── utils.py          sanitize_error(), resolve_env_vars()

prometheus/
├── alerts/           avd_masters.yml          29 rules, 4 groups
├── alertmanager/     alertmanager.yml          routing, inhibition, receivers
│                     templates/avd_masters.tmpl
├── docker-compose.yml
└── prometheus.yml.example

grafana/
├── avd_masters_dashboard.json   25-panel Grafana 10+ dashboard
└── dashboard_gen.py             dashboard source / regeneration script

docs/                GitHub Pages (tkhemraj.github.io/avd-masters)
config/              config.yaml.example
tests/               fixtures.py  (full mock MasterSnapshot + GPUSnapshot)
```

---

## Licence

[MIT](LICENSE)
