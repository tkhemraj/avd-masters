# AVD Masters

**The intelligence platform for organizations that can no longer afford to guess about their GPU infrastructure.**

Most teams running serious GPU workloads on Azure Virtual Desktop know they’re spending heavily. What they don’t know — with any real precision — is whether that spend is justified, where the waste is hiding, or how exposed they are from a governance and compliance standpoint.

Traditional tools either charge you a premium to move your data into Azure Monitor, or they give you dashboards that look sophisticated but leave you with the same hard questions you started with:  
*Is this hardware actually earning its keep?*  
*Which workloads are quietly burning money?*  
*If an auditor walked in tomorrow, how would we prove we’re in control of this environment?*

AVD Masters exists for organizations that have moved past hoping the numbers look fine. It gives you direct truth from the hardware, turns that truth into clear, quantified intelligence, and produces the kind of governance artifacts that actually hold up when scrutiny arrives.

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

## The Signature Experiences

### The Midas Report

Run `python run.py midas` and you don’t get another dashboard full of charts that still require interpretation. You get something rarer: a clear, unvarnished assessment of where your money is going and exactly how much of it is recoverable.

The Midas engine looks at your actual GPU SKUs, their real capabilities, current spend rates, and opportunities for right-sizing, consolidation, and retirement. It then translates that analysis into plain language with specific dollar figures attached — not vague “potential savings” ranges, but concrete monthly and annualized numbers tied to specific hosts and workloads.

This is the report you forward to finance. This is the document that makes the case for change without requiring three follow-up meetings to explain what the data actually means.

### The Touch Command

`python run.py touch` is where the platform shows what it was built for.

In a single, orchestrated run it will:

- Discover your actual AVD GPU estate across subscriptions
- Refresh its understanding of available SKUs directly from Azure
- Run deep Midas analysis on cost, utilization patterns, and optimization potential
- Overlay governance and CMMC 2.0 alignment scoring
- Prepare rich, ready-to-apply Azure tags that carry real financial and operational context
- Generate prioritized remediation playbooks you can actually act on

When email alerting is configured, it will also notify the right people the moment material issues appear — expensive hardware sitting idle, significant projected overruns, or governance gaps that need attention before they become audit findings.

This is not a monitoring tool that happens to have some reports. This is an operational system that can tell you, with unusual clarity, what is happening with the most expensive resources in your environment — and what you should do about it.

---

## Getting Started

Getting started is deliberately straightforward.

```bash
git clone https://github.com/tkhemraj/avd-masters.git
cd avd-masters

pip install -r requirements.txt
cp .env.example .env
```

From there, the two commands that matter most are:

- `python run.py midas` — for immediate intelligence on spend and opportunity.
- `python run.py touch` — for the complete operational workflow, including discovery, analysis, tagging, and governance reporting.

For organizations that need email notifications when material issues arise, the alerting layer can be enabled through a small set of environment variables. Full details are in the project documentation.

Production deployments typically start with read-only discovery and analysis before enabling any write operations such as tag application.

---

### Useful Commands

```bash
python run.py                 # Basic status + catalog
python run.py alerts          # Run full management + alerting session
python run.py cost            # Live FinOps cost attribution demo
python run.py forecast        # Predictive cost forecasting demo
```

---

## Built for Environments Where Governance Actually Matters

Many of the organizations running the largest and most sensitive AVD GPU deployments do not have the luxury of treating infrastructure as a purely technical concern. They operate under contractual, regulatory, or national security requirements that demand demonstrable control.

AVD Masters was designed with that reality in mind.

The governance layer produces more than internal health scores. It generates structured visibility and evidence across the areas that matter most in regulated environments — particularly those aligned with CMMC 2.0 and the underlying NIST SP 800-171 controls. This includes configuration integrity, access and accountability through tagging, risk quantification, and program-level oversight across complex Azure estates.

The goal is not to turn a management tool into a compliance product. The goal is to ensure that the same system you use to understand and optimize your GPU spend can also produce the kind of artifacts that hold up when external parties ask hard questions.

This matters. In environments where GPU infrastructure is both extremely expensive and tightly governed, the ability to speak with precision about cost, risk, and control in the same conversation is a genuine operational advantage.

---

## A Different Kind of Tool

AVD Masters is not trying to be another monitoring platform with better charts.

It is an attempt to build something more useful: a system that respects both the enormous cost of modern GPU infrastructure and the very real governance requirements that come with running it at scale.

The organizations that get the most value from it tend to share a few characteristics. They know their GPU workloads are expensive. They are no longer satisfied with hoping the spend is reasonable. And they operate in environments where “we think we’re in control” is not an acceptable answer when difficult questions are asked.

If that describes your situation, this platform was built with you in mind.

---

## License

MIT License

---

**For teams that have decided it is finally time to understand what their GPUs are actually doing — and what they should be doing instead.**
