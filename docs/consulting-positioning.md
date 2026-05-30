# AVD Masters — Who Built This and Why It Exists

This is not a tool built by a product team that decided AVD needed another dashboard.

It was built by someone who has been in the weeds of this stuff for over 25 years — migrations, M&A collapses, regulated environments, broken profiles, expensive hardware delivering mediocre results — and who got tired of watching the same painful problems repeat themselves in every environment they walked into.

---

## My Background

I started my career at Hypercom, where I learned cryptography and the mechanics of securing credit card transactions at the infrastructure level. That foundation — understanding how systems fail when security isn't designed in — has shaped how I approach everything since.

From there I got deep into Active Directory. MCSE on Windows NT 4.0, then Windows 2000. At the time it was brand new territory, and I built real expertise in enterprise identity and directory infrastructure before most people knew they needed it.

I joined Aelita Software and stayed through the Quest Software acquisition. That's where migrations became my specialty — not small ones, but the kind that Fortune 500 companies call you for when they're consolidating after an M&A event, or collapsing multiple forests, or trying to get off a platform they've outgrown. I've been running those operations since 2004.

I've worked on the infrastructure that became Microsoft 365 before it was called that. When Microsoft was building BPOS — the Business Productivity Online Suite — they were borrowing architecture that we had already built and were selling directly to Verizon. I worked for companies like VANADE that were deeply embedded in Microsoft's ecosystem at the time, building what enterprise cloud delivery would eventually look like.

After Quest, I went to M3 Technology Group in Charlotte — founded by three former Microsoft people — which was acquired by AZALEOS. We built what we called a virtual private cloud and sold it to Verizon Enterprise Services. Verizon's enterprise clients would lease infrastructure sitting in their own data centers rather than managing it themselves. Microsoft eventually acquired that work, and I spent time training the migration engineers who would get organizations off Exchange, Lotus Notes, GroupWise, and early Gmail migrations when nobody really had a practice for that yet.

One of the things I spent a lot of time on in those years was X.400 and X.500 header manipulation — writing scripts that would preserve message threading and reply integrity when you were collapsing six or seven mail systems at once. There weren't great tools for it. You either understood what was happening at the protocol level or you made a mess.

I co-founded Halcyon with Hugh Morrison in Halifax. We built professional services delivery around Active Directory and enterprise management. One of the projects I'm most proud of from that period was the work we did with PwC — helping with their South American theater during a red-green forest worldwide collapse. That kind of work doesn't leave a lot of room for guessing.

I helped a Phoenix-area company attain Microsoft Gold status. They wanted to sell Cisco and VMware. I showed them what they could make doing what I was doing. When I left, they understood.

I spent several years at Dimension Data — acquired by NTT — as a Business Development Manager for their Microsoft line of business. I was trying to move them toward where the real value was. It was hard when the organization's incentives were pointed at data center hardware. I left in 2019.

Since then I've been independent — working with smaller managed service providers that want to deliver world-class Microsoft services without the overhead of a large systems integrator, and building tools like this one.

---

## What I Actually Solve

I'm not trying to compete with Nerdio or any of the monitoring platforms. I'm not selling dashboards.

The environments I walk into have the same problems, over and over:

- **Profile and FSLogix disasters.** This is the number one reason AVD feels terrible. Most organizations have no idea how broken their profile architecture is until I show them. It's not theoretical — it's corrupted containers, busted attach sequences, storage bottlenecks, and users who think VDI just "works like this."

- **Expensive GPU hardware delivering mediocre performance.** Organizations are spending serious money on H100s and A100s and L40Ses and getting user experience that should embarrass the team that set it up. The hardware isn't the problem. The setup, the profile configuration, the encoding pipeline, the monitoring — that's the problem.

- **Cost opacity on GPU infrastructure.** Most environments have no accurate picture of what their GPU spend is actually buying. They know the invoice. They don't know the per-workload, per-session, per-GPU utilization story. AVD Masters was built specifically to fix that.

- **Governance gaps in regulated environments.** I've worked in environments where CMMC 2.0 compliance is not optional and auditors are not patient. Generic tools don't produce the kind of structured evidence those environments require. AVD Masters does.

- **The operational fragility that makes teams feel like they're always one incident away from chaos.** This is cultural and technical. I help fix both.

---

## Why I Built AVD Masters the Way I Did

I'm not a developer by trade. I'm a technologist who knows how to analyze code, has spent decades writing scripts to solve problems that the tools of the moment couldn't handle, and understands what actually matters in production.

AVD Masters is me modernizing the kind of work I've been doing with PowerShell and legacy tooling for years — rebuilding it in Python so it runs against larger, more diverse estates and doesn't become a maintenance liability when Microsoft deprecates the underlying cmdlets.

I used AI to build and augment it. That's not a confession — it's the point. The knowledge base is mine. The operational patterns are things I've learned over 25 years in the field. The code is the vehicle. What you get when you run AVD Masters is the output of that experience turned into something repeatable and scalable, not just something I carry around in my head.

The tool is designed to run against more than one VDI infrastructure. That's deliberate. The environments I work in have increasingly heterogeneous estates — AVD alongside Citrix, alongside other VDI platforms — and the tooling needs to be able to speak across all of that without requiring a different product for each vendor.

---

## Signature Offerings

### AVD Experience & Profile Remediation

Most organizations don't know how bad their profile situation is until I show them. This is the engagement that produces visible results fast — a clear assessment of what's broken, what it's costing, and a hands-on path to fix it.

> "I don't just tell you your profiles are broken. I show you exactly how broken they are, what it's costing you, and how to fix it without making it worse."

### AVD Operational Maturity Assessment

A structured, tool-accelerated assessment that gives leadership an honest picture of where they actually stand — cost, experience, configuration hygiene, governance, operational risk. This is how I win the bigger work. It positions me as the person who sees the whole picture, not just one layer.

### GPU AVD Optimization & Governance

For organizations running serious GPU workloads where both cost control and defensible compliance matter. AVD Masters lets me have both conversations at the same time — "here's exactly how much you're wasting" and "here's the governance evidence you'll need when the auditor arrives."

### Ongoing Operations Partnership

For clients who want ongoing access to someone who actually understands their environment. The toolkit makes me significantly more efficient than a traditional consultant model — I can cover more ground, faster, with more precision.

---

## How I Talk About This

I don't lead with the tool. I lead with the problem.

- *"I've been doing this work since 2004. I built AVD Masters because the tools that existed weren't good enough for the environments I was working in."*
- *"Most organizations running GPU workloads on AVD are leaving real money on the table and delivering user experience that doesn't reflect what they're paying for the hardware. I built something to make that visible."*
- *"I don't sell monitoring. I sell clarity, control, and the ability to stop the same expensive problems from happening again."*

The tool is proof of depth. It shows that I don't just talk about these problems — I've built systems to solve them at scale.

---

## LinkedIn About Section

I've been doing enterprise Microsoft infrastructure work since the days of Windows NT 4.0.

I started at Hypercom learning cryptography and payment security, got deep into Active Directory through the Quest Software years, and have been running migrations — M&A collapses, forest consolidations, cross-platform messaging transitions — since 2004. I've worked on the infrastructure that eventually became Microsoft 365, helped build and sell virtual private cloud services to Verizon Enterprise, and trained migration engineers to get organizations off Exchange, Lotus Notes, GroupWise, and early Gmail when nobody had a real practice for it yet.

Since 2019 I've been independent, working with organizations that are serious about getting AVD right — especially GPU workloads — and with smaller managed service providers that want to deliver world-class Microsoft services without acting like a large systems integrator.

I built AVD Masters because the existing tools weren't good enough for the environments I was seeing. It's not a monitoring platform. It's an operator's toolkit — built to expose the expensive, painful problems that generic tools miss and turn that into clear, quantified, defensible intelligence.

I don't sell dashboards. I sell clarity, control, and the ability to stop making the same expensive mistakes.

If your AVD environment feels more fragile or expensive than it should, I can help.

**Specialties:**
- FSLogix and user profile architecture
- GPU AVD optimization and cost intelligence
- Enterprise migrations (Exchange, AD, M365)
- Governance and compliance in regulated environments (CMMC 2.0 / NIST 800-171)
- Building managed service practices around Microsoft infrastructure

---

## One-Page Capability Overview

**Making AVD Actually Work — Especially When It's Expensive and Regulated**

Most organizations running Azure Virtual Desktop GPU workloads are spending heavily and not getting what they're paying for. The problem is rarely the hardware. It's the profile architecture, the operational gaps, and the absence of real visibility into what the infrastructure is actually doing.

I bring 25+ years of enterprise Microsoft infrastructure experience, a background in identity and migration work that spans Fortune 500 M&A events to CMMC-regulated defense environments, and a purpose-built Python toolkit designed to expose the problems that generic monitoring tools miss.

**What I do:**
- Profile and FSLogix remediation — the number one reason AVD feels broken
- GPU workload optimization — making expensive hardware earn its keep
- Cost intelligence — accurate FinOps attribution, not guesswork
- Governance and compliance evidence — built for regulated environments
- Migration and consolidation — from legacy platforms to modern AVD at scale

**What makes this different:**
I'm not another consultant with another tool. I built the tool because the tools that existed weren't good enough. It reflects 25 years of operational pattern recognition turned into something repeatable, scalable, and honest.

You get clarity fast, and a clear path to fix the problems that are actually costing you.
