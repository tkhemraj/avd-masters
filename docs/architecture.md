# Architecture

**AVD Masters** is an intelligence and governance platform for high-value GPU workloads running on Azure Virtual Desktop. It is deliberately designed to be simple to operate, extremely accurate on fractional GPUs, and genuinely useful for both operational teams and governance/compliance stakeholders.

## Core Design Principles

- **Direct Hardware Truth** — We talk to the metal. No reliance on sampled Azure Monitor data.
- **Fractional GPU Precision** — The `GpuSpec` model is the single source of truth for what each SKU actually delivers (including 1/6, 1/3, 1/2 partitions).
- **Intelligence Over Dashboards** — Raw signals are collected; rich, actionable analysis (Midas) is computed on demand.
- **Governance by Default** — Especially strong support for regulated environments (CMMC 2.0 / NIST 800-171).
- **Extensible Signals Layer** — One clean data model (`HostSignal` + `FleetSignals`) that powers cost, performance, and experience analysis.
- **No Vendor Lock-in Tax** — Works great with local collection. Optional Azure integration only where it adds real value.

## High-Level Data Flow

```
Discovery (Azure APIs)
        ↓
    Catalog Lookup + Dynamic SKU Refresh
        ↓
Signals Collection (WinRM / SSH / nvidia-smi / rocm-smi + latency probes)
        ↓
    HostSignal + FleetSignals
        ↓
Midas Intelligence Engine  ←  Governance / CMMC Layer
        ↓
Actionable Output:
  - Quantified savings opportunities
  - User Experience insights (latency, frame times)
  - Rich Azure tags
  - Remediation playbooks
  - Alerts (console + email)
```

## Key Components

### 1. Catalog (`catalog.py`)
The foundation. Defines every relevant Azure GPU SKU with precise `gpu_count`, VRAM, generation, and retirement status. Supports both static definitions and live enrichment via `sku_discovery.py`.

### 2. Signals Layer (`signals.py`)
The modern heart of the platform.

- `HostSignal`: Rich per-host telemetry (utilization + latency + performance metrics).
- `FleetSignals`: Aggregated view with computed scores (waste score, experience score).
- Pluggable collectors (`SimulatedCollector`, `LocalCollector` pattern for real WinRM/SSH collection).

This layer now treats **user experience** (frame times, input latency) with the same importance as cost/utilization.

### 3. Midas Intelligence (`midas.py`)
The signature "everything it touches turns to gold" engine.

- Analyzes cost, configuration, and now user experience signals.
- Produces `GoldenOpportunity` objects ranked by real financial impact.
- Generates the famous `MidasTouchResult` with brutal truth + prioritized actions.
- Can trigger email notifications when situations are genuinely funky.

### 4. Governance & Compliance (`governance.py`)
Enterprise-grade oversight:

- Fleet Health Score
- Cross-subscription rollups
- CMMC 2.0 alignment reporting (explicit mapping to AC, AU, CM, IR, PM, RA, SI domains)
- Policy violation detection

### 5. Cost & Tagging (`cost.py`)
Extremely accurate GPU-attributable costing:

- Full VM price × `gpu_count` (handles fractions correctly)
- Live Azure Retail Prices API + high-quality fallbacks
- Rich `avd_masters:*` tags for chargeback and governance

### 6. Alerting (`alerting.py`)
Rule-based engine with email support. Now includes latency/experience rules in addition to cost and utilization.

## Extending the Platform (Gold Standard Guidance)

The architecture is intentionally extensible:

1. **New Metrics** — Extend `HostSignal` with additional fields. Update collectors accordingly.
2. **New Intelligence** — Add opportunity types in `midas.py` (see `bad_experience_on_expensive_hardware` as example).
3. **New Collectors** — Implement the `SignalCollector` interface. The `LocalCollector` pattern shows the expected shape for real WinRM/SSH + smi collection.
4. **New Alert Rules** — Add functions following the `rule_*` pattern and register them in `create_default_alert_engine()`.

All new capabilities should flow through the Signals → Midas/Governance pipeline so they benefit from the full power of the platform.

---

*Architecture should make the hard things obvious and the obvious things trivial.*
