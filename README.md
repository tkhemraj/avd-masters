# GROKY 2.0

**The professional GPU monitoring and management platform for Azure Virtual Desktop.**

> Direct hardware truth. Real alerts. Actionable intelligence.  
> Zero Azure Monitor tax.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/badge/GitHub-tkhemraj/groky-black?style=flat&logo=github)](https://github.com/tkhemraj/groky)
[![Status](https://img.shields.io/badge/status-active%20development-orange)](https://github.com/tkhemraj/groky)

---

## The Problem

Most tools for monitoring GPU workloads on AVD are either:

- **Expensive** — Heavy reliance on Azure Monitor + Log Analytics
- **Inaccurate** — Sampled data that fails on fractional GPUs
- **Shallow** — Pretty dashboards with very little actionable value

**GROKY 2.0 exists to fix this.**

---

## What GROKY Actually Delivers

| Area                    | What You Get                                                                 |
|-------------------------|-------------------------------------------------------------------------------|
| **Hardware Truth**      | Direct `nvidia-smi` / `rocm-smi` collection. No sampling lies.               |
| **Fractional GPUs**     | Proper modeling of 1/6, 1/3, 1/2 partitions (most tools get this wrong)       |
| **Modern Hardware**     | 41+ current SKUs including H100, H200, MI300X, L40S, etc.                    |
| **Real Alerts**         | Actionable alerts on utilization, cost, imbalance, and forecasting           |
| **FinOps Visibility**   | Accurate cost-per-second + auto-generated Azure cost tags                    |
| **Intelligence**        | Forecasting, optimization recommendations, and governance                    |

---

## Quick Start

```bash
git clone https://github.com/tkhemraj/groky.git
cd groky

pip install -r requirements.txt
cp .env.example .env
# Configure your Azure + WinRM/SSH access

python run.py
```

Then open **http://localhost:8080**

---

### Useful Commands

```bash
python run.py                 # Basic status + catalog
python run.py alerts          # Run full management + alerting session
python run.py cost            # Live FinOps cost attribution demo
python run.py forecast        # Predictive cost forecasting demo
```

---

## Documentation

| Document                    | Purpose                                      |
|----------------------------|----------------------------------------------|
| [FEATURES.md](FEATURES.md) | Enterprise features for Microsoft customers  |
| [MEGA-FEATURES.md](MEGA-FEATURES.md) | Ambitious long-term vision & platform direction |
| [docs/index.html](docs/index.html) | Beautiful interactive product demo           |

---

## Philosophy

- **Direct over sampled** — We talk to the metal.
- **Useful over pretty** — Alerts and recommendations that help you manage.
- **Low cost by default** — No forced expensive Azure services.
- **Enterprise ready** — Built with FinOps, governance, and large-scale operations in mind.

---

## Current Focus

We are actively building real, usable management capabilities:

- Working alerting engine with practical rules
- Cost attribution and Azure tagging
- Forecasting and optimization recommendations
- Strong CLI experience for day-to-day operations

This is not a marketing project. It's a tool designed to help teams that actually run expensive GPU infrastructure on Azure.

---

## License

MIT License — Use it, fork it, improve it.

---

**Built for people who need to know what's actually happening with their GPUs — and what to do about it.**
