# Getting Started with GROKY 2.0

This guide will get you running quickly with the right mindset.

---

## Prerequisites

- Python 3.11+
- Network access to your AVD session hosts (WinRM or SSH)
- Azure permissions to read Host Pools and VM sizes (Reader + Desktop Virtualization Reader recommended)

---

## Installation

```bash
git clone https://github.com/tkhemraj/groky.git
cd groky

pip install -r requirements.txt
```

---

## Configuration

```bash
cp .env.example .env
```

Edit `.env` with at least:

- Azure credentials (or just use `az login`)
- Connection details for your session hosts (WinRM is default)

You can also create a `hosts.yaml` for per-host overrides.

---

## First Run

```bash
python run.py
```

GROKY will:
1. Load the world-class GPU catalog
2. Start the web server on port 8080
3. Begin discovery + collection immediately

Open **http://localhost:8080**

---

## First Impressions

The first few minutes will mostly show "unknown" or partial data while discovery and the first polls complete. This is normal.

Within 1-2 poll cycles you should start seeing real GPU metrics.

---

## Next Steps

- Read the [Catalog documentation](catalog.md) — it's genuinely special
- Explore the architecture
- Start thinking about how you want alerts and long-term storage

Welcome to the good side of GPU monitoring.
