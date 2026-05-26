# AVD Masters Toolkit Guide

This document describes the **AVD Masters Toolkit** — the practical, operator-focused layer of the platform.

## Philosophy

AVD is powerful but extremely easy to make painful through common configuration mistakes (especially around user profiles).

Most people who set up AVD are not AVD experts. They make the same painful mistakes repeatedly:
- Bad or missing FSLogix configuration
- Terrible autoscale rules
- Image and driver drift across pools
- Accumulating orphaned resources

AVD Masters Toolkit exists to make these problems visible and actionable using a Python-first, low-PowerShell approach.

## Key Modules

### `toolkit.py`
High-level utilities for real operational problems:
- Host pool autoscale recommendations (experience-aware)
- Image & driver drift detection
- Orphaned resource hunting
- Quick environment health snapshots
- Azure-side profile storage analysis

### `profiles.py`
Deep focus on the #1 source of AVD misery: user profiles and FSLogix.

Strong emphasis on being able to do valuable analysis from the Azure control plane (storage accounts, file shares, VHD patterns) so you don't have to perfectly instrument every single VM.

## Recommended Workflow

1. Run `python run.py touch` regularly (this is your main operational command).
2. Use `python run.py profiles` when you want to specifically audit profile/FSLogix configuration.
3. Use `python run.py midas` when you want the intelligence view (cost + experience + setup debt).
4. Wire email alerts for the things that actually matter to your team.

## Extending the Toolkit

When adding new capabilities:
- Prefer Azure SDK analysis over inside-VM execution.
- When host data is needed, prefer stable direct commands.
- Feed insights into Midas as new opportunity types when possible.
- Keep the voice direct, useful, and a little bit spicy.

Good architecture makes the painful, recurring problems in AVD obvious and fixable.
