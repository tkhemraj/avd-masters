# Architecture

AVD Masters is built with deliberate simplicity and high standards.

## Core Principles

- **Agentless first** — We talk directly to the metal via standard tools (`nvidia-smi`, `rocm-smi`).
- **Catalog as foundation** — The GPU catalog is the single source of truth. Everything else derives from it.
- **Raw data, smart analysis** — We store raw samples and compute insight on demand.
- **No vendor lock-in tax** — You are not forced into expensive Azure data services.

## High-Level Flow

1. **Discovery** — Azure APIs are used (optionally) to find AVD session hosts and resolve their VM SKUs against the catalog.
2. **Collection** — WinRM or SSH collectors run the appropriate GPU command on each host.
3. **Storage** — Raw samples go into local SQLite.
4. **Analysis** — On every API request, we build rich `HostStatus` and `PoolAnalysis` objects.
5. **Presentation** — FastAPI serves both the web dashboard and a clean JSON API.

## Why This Design Wins

Most solutions either:
- Push everything into Azure Monitor (expensive + lossy)
- Require installing agents everywhere (operational burden)
- Use outdated SKU data (wrong math on fractional GPUs)

AVD Masters does none of these.

---

## Current Layers (Foundation Phase)

- `avd_masters/catalog.py` — Best-in-class SKU intelligence
- `avd_masters/models.py` — Clean, typed data contracts
- `avd_masters/types.py` — Shared primitives

The collection, scheduling, and dashboard layers are coming next — built on this solid base.

---

*Good architecture is invisible until you need to extend it.*
