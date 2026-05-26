# GROKY GPU Catalog

This is the heart of GROKY 2.0.

While other tools are still using stale 2025-era SKU lists, GROKY ships with a rich, accurate, and queryable model of **real** Azure GPU hardware — including proper fractional GPU support.

---

## Why This Catalog Matters

Most monitoring solutions either:
- Don't understand fractional GPUs at all
- Treat every partition like a full GPU
- Have outdated data

GROKY's `GpuSpec` knows the truth:

- Exact `gpu_count` (supports 0.166 = 1/6, 0.25 = 1/4, etc.)
- Assigned VRAM per partition
- Generation (Hopper, Blackwell, Ada, CDNA3...)
- Retirement status

---

## Key Capabilities

```python
import groky.catalog as c

# Rich objects
spec = c.lookup("Standard_ND96isr_H200_v5")
print(spec.pretty())
# → H200 (1119.5 GB) [NVIDIA] • Hopper — 8× H200 141GB

print(spec.is_fractional)   # False
print(spec.vram_gb)         # 1119.5

# Powerful queries
c.get_high_end_nodes()      # All 4+ GPU dense nodes
c.get_fractional_skus()     # Everything with partitions
c.get_by_generation("Hopper")
c.get_skus_by_model("H100")
```

---

## Current Coverage (41 SKUs)

### NVIDIA — Current Generation

**Hopper (H100 / H200)**
- Full and fractional NCads_H100_v5 series
- Dense ND_H100_v5 and ND_H200_v5 8x nodes
- Proper 1/6, 1/3, 1/2, and full partitions

**Ampere (A100)**
- NC_A100_v4 and dense ND nodes

**Ada Lovelace**
- L40S series
- Professional RTX 6000 Ada series

**Legacy (still tracked)**
- NVv3 (M60) — retiring

### AMD

- Radeon PRO V620 (NGads)
- Radeon PRO V710 v5 fractional family
- MI300X 8x dense nodes (CDNA3)
- Legacy MI25 (retiring)

---

## Full SKU Reference

> For the complete machine-readable list, see `groky/catalog.py`

### Notable Modern SKUs

| SKU                              | GPU       | Count | VRAM     | Notes                          |
|----------------------------------|-----------|-------|----------|--------------------------------|
| Standard_ND96isr_H200_v5        | H200     | 8     | ~1120 GB | Current high-end dense node    |
| Standard_ND96isr_H100_v5        | H100     | 8     | 640 GB   | 8× 80GB Hopper                 |
| Standard_NC40ads_H100_v5        | H100     | 1     | 94 GB    | High-memory H100 variant       |
| Standard_NC32ads_H100_v5        | H100     | 1     | 80 GB    | Standard full H100             |
| Standard_NC4ads_H100_v5         | H100     | 1/6   | 8 GB     | Entry-level fractional Hopper  |
| Standard_nd96is_mi300x_v5       | MI300X   | 8     | 1536 GB  | 8× AMD 192GB beast             |
| Standard_NV36ads_A10_v5         | A10      | 1     | 24 GB    | Still excellent for VDI        |

---

## Design Philosophy

The catalog is deliberately over-engineered compared to most tools because **fractional GPUs are the future**, and most monitoring solutions are still pretending they don't exist.

Every `GpuSpec` is a first-class object with computed properties so the rest of the system never has to do math on SKU strings again.

---

**This catalog is why GROKY already feels different.**
