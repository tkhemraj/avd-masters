# AVD Masters

**The enterprise GPU management and intelligence platform for Azure Virtual Desktop.**

AVD Masters delivers direct hardware truth, actionable intelligence, and professional governance for organizations running high-value GPU workloads on Azure Virtual Desktop — without the cost and limitations of traditional monitoring approaches.

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/badge/GitHub-tkhemraj/avd-masters-black?style=flat&logo=github)](https://github.com/tkhemraj/avd-masters)
[![Status](https://img.shields.io/badge/status-active%20development-orange)](https://github.com/tkhemraj/avd-masters)

---

## The Challenge

Organizations running GPU-accelerated AVD workloads face a consistent set of problems:

- **High cost of traditional monitoring** — Heavy dependence on Azure Monitor and Log Analytics creates significant ongoing expense.
- **Inaccurate data on fractional GPUs** — Most tools fail to properly account for vGPU partitioning (1/6, 1/3, 1/2, etc.).
- **Lack of actionable insight** — Dashboards show metrics, but rarely deliver clear, prioritized recommendations with quantified business impact.
- **Governance and compliance pressure** — Especially for organizations subject to CMMC 2.0, NIST 800-171, or other regulated environments.

AVD Masters was built to solve these problems with a direct, intelligence-first approach.

---

## Core Capabilities

| Area                    | What You Get                                                                 |
|-------------------------|-------------------------------------------------------------------------------|
| **Hardware Truth**      | Direct `nvidia-smi` / `rocm-smi` collection. No sampling lies.               |
| **Fractional GPUs**     | Proper modeling of 1/6, 1/3, 1/2 partitions (most tools get this wrong)       |
| **Modern Hardware**     | 41+ current SKUs including H100, H200, MI300X, L40S, etc.                    |
| **Real Alerts**         | Actionable alerts on utilization, cost, imbalance, and forecasting           |
| **FinOps Visibility**   | Accurate cost-per-second + auto-generated Azure cost tags                    |
| **Intelligence**        | Forecasting, optimization recommendations, and governance                    |

---

---

## Signature Experiences

### `midas`
Pure intelligence. Run `python run.py midas` to receive a high-signal report showing current spend, recoverable savings opportunities, and prioritized actions — written in clear, direct language.

### `touch`
The full orchestrated experience. `python run.py touch` performs discovery, runs Midas analysis, overlays governance and CMMC 2.0 alignment, prepares rich Azure tags, and generates remediation playbooks.

When configured, `touch` can also send targeted email notifications when material issues are detected.

---

## Getting Started

```bash
git clone https://github.com/tkhemraj/avd-masters.git
cd avd-masters

pip install -r requirements.txt
cp .env.example .env

# Configure Azure credentials and (optionally) WinRM/SSH access for direct collection
python run.py
```

### Recommended Commands

```bash
python run.py midas                    # Intelligence report with quantified opportunities
python run.py touch                    # Full discovery + analysis + governance + playbooks
python run.py touch --apply-tags       # Same as above, with tag application (use with care)
python run.py discover                 # Focused discovery and live SKU refresh
```

For production use, review `governance.py` for CMMC configuration guidance and `alerting.py` for email notification setup.

```bash
git clone https://github.com/tkhemraj/avd-masters.git
cd avd-masters

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

## Enterprise Governance

AVD Masters includes first-class support for organizations operating under regulatory requirements:

- **Fleet Health Scoring** — A single, meaningful metric for leadership visibility.
- **Cross-Subscription Rollups** — Governance views across complex Azure estates.
- **CMMC 2.0 Alignment** — Explicit mapping to relevant NIST 800-171 / CMMC 2.0 domains (AC, AU, CM, IR, PM, RA, SI), with honest coverage assessment and evidence generation suitable for audits.

See `governance.py` for the detailed rationale and control mappings.

---

## Philosophy

- **Direct over sampled** — We collect truth from the hardware itself.
- **Actionable over decorative** — Every output is designed to drive a decision.
- **Cost-efficient by default** — No forced reliance on expensive Azure data services.
- **Enterprise-grade governance** — Built with FinOps, risk management, and regulated environments in mind.
- **Professional by design** — Clear documentation, predictable behavior, and output suitable for technical and business stakeholders.

---

## Current Focus

AVD Masters is under active development with emphasis on:

- High-fidelity intelligence (Midas) that consistently surfaces material savings and risk
- Production-grade signals collection patterns
- Deep enterprise governance, including CMMC 2.0 support
- One-command operational experiences (`touch`)

The project is designed for teams that manage expensive GPU infrastructure and need both operational excellence and defensible governance artifacts.

---

## License

MIT License

---

**Built for organizations that need to understand exactly what is happening with their GPUs — and what to do about it.**
