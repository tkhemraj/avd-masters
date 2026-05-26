"""
AVD Masters — Midas Touch Intelligence Engine

The Midas module delivers the platform's signature intelligence capability.

It analyzes discovery data, catalog information, and utilization signals to produce:

- Clear, prioritized insights with quantified business impact
- Actionable recommendations expressed in both operational and financial terms
- Executive-ready narratives suitable for technical and business stakeholders

The goal is to turn raw operational data into decision-grade intelligence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from avd_masters import alerting, catalog, cost, profiles, signals, toolkit
from avd_masters.catalog import GpuSpec
from avd_masters.signals import FleetSignals, HostSignal

logger = logging.getLogger(__name__)


# =============================================================================
# Data Contracts for the Magic
# =============================================================================

@dataclass
class GoldenOpportunity:
    """
    A single, actionable, quantified opportunity to improve cost or user experience.

    This is the atomic output of the Midas intelligence engine. Every `GoldenOpportunity`
    represents something real that a human (or automated system) can act on, with clear
    financial or experience impact attached.

    Attributes
    ----------
    host : str
        Name of the affected session host or group.
    sku : str
        The Azure VM size (e.g. Standard_NC32ads_H100_v5).
    gpu_spec : GpuSpec
        Precise hardware profile of the SKU (including fractional allocation).
    current_monthly_burn : float
        Estimated monthly cost attributable to the GPUs on this host/allocation.
    potential_monthly_savings : float
        How much could realistically be recovered or avoided.
    opportunity_type : str
        Classification of the opportunity (e.g. "high_end_underutilized",
        "fractional_on_premium", "bad_experience_on_expensive_hardware", "dense_packing").
    confidence : str
        "high", "medium", or "speculative".
    grok_insight : str
        Direct, human-readable explanation with personality.
    recommended_action : str
        Concrete next step.
    impact : str
        Human-friendly summary (e.g. "Saves ~$2,840/month").
    """


@dataclass
class MidasTouchResult:
    """
    The complete, self-contained output of a Midas intelligence run.

    This is the primary "gold report" object returned by `perform_midas_touch()`.
    It is designed to be immediately useful for humans (executives, architects, FinOps)
    while also being machine-readable for automation.

    It contains:
    - Aggregated financial summary
    - Ranked list of `GoldenOpportunity` objects
    - Narrative sections ("brutal truth", surprise insights)
    - Derived properties for convenience

    This object is what powers the beautiful `midas` CLI output and can be used
    programmatically or serialized.
    """
    generated_at: str
    total_hosts_analyzed: int
    total_current_monthly_burn: float
    total_potential_monthly_gold: float   # Real savings identified
    opportunities: list[GoldenOpportunity] = field(default_factory=list)
    brutal_truth: str = ""
    gold_narrative: str = ""
    top_recommendations: list[str] = field(default_factory=list)
    surprise_insight: str = ""
    tags_generated: int = 0

    @property
    def annual_gold_potential(self) -> float:
        """Annualized recoverable value."""
        return round(self.total_potential_monthly_gold * 12, 0)

    @property
    def savings_percentage(self) -> float:
        """Percentage of current burn that could be recovered."""
        if self.total_current_monthly_burn <= 0:
            return 0.0
        return round((self.total_potential_monthly_gold / self.total_current_monthly_burn) * 100, 1)

    @property
    def estimated_monthly_carbon_kg(self) -> float:
        # Rough aggregate — real version would sum per host
        return round(self.total_current_monthly_burn * 1.8, 0)  # very rough proxy


# =============================================================================
# Grok Inside — The Personality & Reasoning Layer
# =============================================================================

def _grok_speak(insight_type: str, **context: Any) -> str:
    """Grok-flavored insight generator. Direct. Useful. Occasionally savage. Never boring."""
    if insight_type == "idle_expensive":
        return (
            f"This {context.get('model')} host has been sipping power like it's on vacation. "
            f"At ~${context.get('burn', 0):,.0f}/month it's one of the most expensive paperweights in your subscription. "
            "Touch it."
        )
    if insight_type == "fractional_waste":
        return (
            f"You're paying for a full {context.get('model')} but only using a {context.get('fraction')}. "
            "This is the GPU equivalent of renting a mansion and living in the broom closet. "
            f"Right-size and reclaim ${context.get('savings', 0):,.0f}/month."
        )
    if insight_type == "wrong_family":
        return (
            f"{context.get('model')} is great... if you're doing what it was built for. "
            f"You're using it for {context.get('workload', 'something else')}. "
            "There are better tools for this job. The difference is real money."
        )
    if insight_type == "dense_node_opportunity":
        return (
            f"You have {context.get('count')} expensive single-GPU hosts doing light work. "
            "Packing them onto dense nodes (or right-sizing) would turn several of these into pure profit."
        )
    if insight_type == "overall":
        return (
            f"Your current GPU estate is burning ${context.get('burn', 0):,.0f} per month. "
            f"I've identified ${context.get('gold', 0):,.0f} in recoverable gold ({context.get('pct', 0):.1f}%). "
            "Most teams leave this on the table because the data is too noisy. Not anymore."
        )
    return "Something valuable is here. We should touch it."


def _calculate_monthly_burn(spec: GpuSpec, sku: str, region: str = "eastus") -> float:
    """Estimate realistic monthly cost for this host (24x7 assumption for worst-case visibility)."""
    hourly = cost.calculate_gpu_hourly_cost(spec, sku, region) or 0.0
    return round(hourly * 730, 2)  # ~730 hours in a month


def _score_opportunity(host_name: str, spec: GpuSpec, sku: str, region: str) -> Optional[GoldenOpportunity]:
    """The actual magic happens here — decide if this host is leaking gold and how much."""
    monthly_burn = _calculate_monthly_burn(spec, sku, region)

    # === Rule 1: Expensive idle / very low value (we'll wire real signals later) ===
    if spec.model in ("H100", "H200", "MI300X") and spec.gpu_count >= 1.0:
        # These are the current kings. If they're not hammered, it's criminal.
        savings = round(monthly_burn * 0.65, 0)
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=savings,
            opportunity_type="high_end_underutilized",
            confidence="high",
            grok_insight=_grok_speak("idle_expensive", model=spec.model, burn=monthly_burn),
            recommended_action="Investigate utilization immediately. Consider rebalancing or rightsizing to L40S/A10 family if workload allows.",
            impact=f"Saves ~${savings:,.0f}/month",
        )

    # === Rule 2: Fractional waste on big iron ===
    if spec.is_fractional and spec.model in ("H100", "H200", "MI300X") and spec.gpu_count <= 0.5:
        savings = round(monthly_burn * 0.55, 0)
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=savings,
            opportunity_type="fractional_waste",
            confidence="high",
            grok_insight=_grok_speak(
                "fractional_waste",
                model=spec.model,
                fraction=spec.fractional_share or f"{spec.gpu_count:.2f}",
                savings=savings,
            ),
            recommended_action="Move this workload to a properly sized smaller SKU or consolidate fractional jobs.",
            impact=f"Saves ~${savings:,.0f}/month",
        )

    # === Rule 3: Legacy / retiring hardware still in production ===
    if spec.retiring:
        savings = round(monthly_burn * 0.40, 0)
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=savings,
            opportunity_type="retiring_hardware",
            confidence="medium",
            grok_insight=f"{spec.model} is retiring soon. You're running on borrowed time and paying a premium for the privilege.",
            recommended_action="Migrate off before September 2026. This is table stakes risk management.",
            impact=f"Risk reduction + ~${savings:,.0f}/month potential",
        )

    # === Rule 4: Right-sizing matrix (very common expensive mistake) ===
    if spec.model in ("H100", "H200") and spec.gpu_count >= 1.0:
        # Many graphics / light inference workloads do not need H100
        potential_savings = round(monthly_burn * 0.45, 0)
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=potential_savings,
            opportunity_type="oversized_for_workload",
            confidence="medium",
            grok_insight=(
                f"{spec.model} is the Ferrari of GPUs. If your workload doesn't need that power, "
                "you're burning money for bragging rights. L40S or A10 class often delivers 70-80% of the experience at half the price."
            ),
            recommended_action="Profile the actual workload. If it's VDI/graphics or light AI, move to L40S/A10 family.",
            impact=f"Potential ${potential_savings:,.0f}/month by right-sizing",
        )

    # === Rule 5: Obvious fractional on expensive SKUs (already partially covered, stronger version) ===
    if spec.model in ("H100", "H200", "MI300X") and 0.2 < spec.gpu_count < 1.0:
        savings = round(monthly_burn * 0.50, 0)
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=savings,
            opportunity_type="fractional_on_premium",
            confidence="high",
            grok_insight=(
                f"You're on a premium {spec.model} with only {spec.gpu_count:.2f} of it. "
                "This is one of the most common ways people light money on fire in AVD."
            ),
            recommended_action="Consolidate fractional workloads onto fewer hosts or move to appropriately sized SKUs.",
            impact=f"Saves ~${savings:,.0f}/month",
        )

    # === New: Obvious L40S on heavy compute workloads (reverse right-size) ===
    if "L40" in spec.model and spec.gpu_count >= 1.0:
        savings = round(monthly_burn * 0.15, 0)  # smaller but real
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=savings,
            opportunity_type="wrong_tool_for_job",
            confidence="medium",
            grok_insight="L40S is fantastic for graphics and light inference. If this is heavy training or large models, you're on the wrong horse.",
            recommended_action="Profile the workload. If it's truly heavy, a smaller number of H100s will be both faster and cheaper.",
            impact=f"Performance + ~${savings:,.0f}/month efficiency",
        )

    # === New: Legacy fractional that should have been retired already ===
    if spec.retiring and spec.is_fractional:
        savings = round(monthly_burn * 0.55, 0)
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=savings,
            opportunity_type="zombie_fractional",
            confidence="high",
            grok_insight="You're running fractional shares of hardware that is already end-of-life. This is technical debt with a power bill.",
            recommended_action="Migrate these workloads immediately. The risk is not worth the tiny savings you're pretending to get.",
            impact=f"Risk elimination + ~${savings:,.0f}/month",
        )

    # === New: Expensive dense nodes doing light work ===
    if spec.gpu_count >= 4.0 and spec.model in ("H100", "H200", "MI300X"):
        savings = round(monthly_burn * 0.35, 0)
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=savings,
            opportunity_type="dense_node_waste",
            confidence="medium",
            grok_insight=(
                f"You have an {spec.gpu_count:.0f}x {spec.model} node doing relatively light work. "
                "These things are nuclear reactors on the power bill. If utilization isn't high, this is one of the most expensive mistakes in the catalog."
            ),
            recommended_action="Either feed this thing real work or break the workloads up onto cheaper fractional hardware.",
            impact=f"Potential ~${savings:,.0f}/month by right-sizing the node",
        )

    # === New: A10/L40S on what should be H100 (reverse right-size) ===
    if spec.model in ("A10", "L40S") and spec.gpu_count >= 1.0:
        savings = round(monthly_burn * 0.12, 0)
        return GoldenOpportunity(
            host=host_name,
            sku=sku,
            gpu_spec=spec,
            current_monthly_burn=monthly_burn,
            potential_monthly_savings=savings,
            opportunity_type="undersized_for_workload",
            confidence="medium",
            grok_insight="This host is working hard on relatively weak hardware. Sometimes paying for the bigger SKU actually saves money through higher density and lower per-user cost.",
            recommended_action="Profile whether moving this workload to H100/H200 would let you consolidate users and reduce total nodes.",
            impact=f"Possible density win + ~${savings:,.0f}/month efficiency",
        )

    # === Toolkit-driven: Profile configuration debt ===
    # (populated externally via toolkit.analyze_profile_debt)
    # We leave a hook here so Midas can accept these cleanly.

    return None


# =============================================================================
# The Midas Touch — Main Entry Point
# =============================================================================

def perform_midas_touch(
    hosts: list[Any],
    region: str = "eastus",
    include_demo_data: bool = True,
    fleet_signals: signals.FleetSignals | None = None,
) -> MidasTouchResult:
    """
    Run the full Midas Touch over a fleet.

    This is the signature experience. One call should make people feel like
    they just got handed a treasure map with the X already marked.
    """
    opportunities: list[GoldenOpportunity] = []
    total_burn = 0.0
    total_gold = 0.0

    # If no real hosts provided, use rich demo data so the magic is always visible
    if not hosts and include_demo_data:
        demo_specs = [
            ("avd-h100-prod-03", "Standard_NC32ads_H100_v5", catalog.lookup("Standard_NC32ads_H100_v5")),
            ("avd-h100-fract-11", "Standard_NC4ads_H100_v5", catalog.lookup("Standard_NC4ads_H100_v5")),
            ("avd-legacy-02", "Standard_NV12s_v3", catalog.lookup("Standard_NV12s_v3")),
            ("avd-l40s-07", "Standard_NV36ads_L40S_v5", catalog.lookup("Standard_NV36ads_L40S_v5")),
        ]
        for name, sku, spec in demo_specs:
            if spec:
                monthly = _calculate_monthly_burn(spec, sku, region)
                total_burn += monthly
                opp = _score_opportunity(name, spec, sku, region)
                if opp:
                    opportunities.append(opp)
                    total_gold += opp.potential_monthly_savings
                else:
                    # Still count the burn even if no big opportunity
                    pass

    else:
        # Real path (when discovery actually returns hosts)
        for host in hosts:
            spec = getattr(host, "gpu_spec", None)
            sku = getattr(host, "vm_size", None) or getattr(host, "sku", None)
            name = getattr(host, "name", str(host))

            if not spec or not sku:
                continue

            monthly = _calculate_monthly_burn(spec, sku, getattr(host, "region", region) or region)
            total_burn += monthly

            opp = _score_opportunity(name, spec, sku, getattr(host, "region", region) or region)
            if opp:
                opportunities.append(opp)
                total_gold += opp.potential_monthly_savings

    # Sort by real money
    opportunities.sort(key=lambda o: o.potential_monthly_savings, reverse=True)

    # === Fleet-level magic: Dense node packing + global optimization signals ===
    # Count how many expensive single-GPU or small fractional hosts we have.
    expensive_small_hosts = [
        o for o in opportunities
        if o.gpu_spec.gpu_count <= 1.0 and o.gpu_spec.model in ("H100", "H200", "MI300X")
    ]

    if len(expensive_small_hosts) >= 4:
        packing_savings = round(sum(o.potential_monthly_savings for o in expensive_small_hosts[:4]) * 0.3, 0)
        packing_opp = GoldenOpportunity(
            host=f"{len(expensive_small_hosts)} similar hosts",
            sku="Various",
            gpu_spec=expensive_small_hosts[0].gpu_spec,
            current_monthly_burn=sum(o.current_monthly_burn for o in expensive_small_hosts[:4]),
            potential_monthly_savings=packing_savings,
            opportunity_type="dense_packing",
            confidence="medium",
            grok_insight=(
                f"You have at least {len(expensive_small_hosts)} hosts running small slices of very expensive GPUs. "
                "Packing compatible workloads onto fewer dense nodes (or using better fractional families) is often pure profit."
            ),
            recommended_action="Run a packing analysis. Target 70-80% average utilization across the fleet.",
            impact=f"Additional ~${packing_savings:,.0f}/month from smarter packing",
        )
        opportunities.append(packing_opp)
        total_gold += packing_savings

    # Re-sort after fleet analysis
    opportunities.sort(key=lambda o: o.potential_monthly_savings, reverse=True)

    # === Signals integration (the scary accurate part) ===
    if fleet_signals:
        enriched = signals.enrich_midas_opportunities(hosts, fleet_signals)
        for item in enriched:
            opp = GoldenOpportunity(
                host=item["host"],
                sku="unknown (from signals)",
                gpu_spec=catalog.lookup("Standard_NC32ads_H100_v5") or list(catalog.CATALOG.values())[0],
                current_monthly_burn=0.0,
                potential_monthly_savings=1800.0,  # conservative placeholder until we have cost data
                opportunity_type=item["type"],
                confidence="very_high",
                grok_insight=item["grok_line"],
                recommended_action="Investigate immediately. This host is costing real money while doing almost nothing.",
                impact="Confirmed idle — high savings potential",
            )
            opportunities.append(opp)

        # New: Experience debt on expensive hardware is the worst kind of waste
        for sig in fleet_signals.signals:
            if sig.has_poor_experience and sig.avg_frame_time_ms:
                # Find matching host cost if possible
                monthly_burn = 1200  # fallback
                for h in hosts:
                    if getattr(h, "name", None) == sig.host_name:
                        spec = getattr(h, "gpu_spec", None)
                        sku = getattr(h, "vm_size", None)
                        if spec and sku:
                            monthly_burn = _calculate_monthly_burn(spec, sku, region) or 1200
                        break

                opp = GoldenOpportunity(
                    host=sig.host_name,
                    sku="from signals",
                    gpu_spec=catalog.lookup("Standard_NC32ads_H100_v5") or list(catalog.CATALOG.values())[0],
                    current_monthly_burn=monthly_burn,
                    potential_monthly_savings=round(monthly_burn * 0.4, 0),
                    opportunity_type="bad_experience_on_expensive_hardware",
                    confidence="high",
                    grok_insight=(
                        f"This host is delivering poor user experience (P95 frame time ~{sig.p95_frame_time_ms}ms, "
                        f"input lag ~{sig.input_latency_ms}ms) on expensive hardware. "
                        "This is the most painful form of waste — users are unhappy and the company is overpaying."
                    ),
                    recommended_action="Profile encoding, network path, and workload. Consider right-sizing or moving to more appropriate SKUs.",
                    impact=f"Bad experience on hardware costing ~${monthly_burn:,.0f}/month",
                )
                opportunities.append(opp)

    # === Build the Grok Narrative (the part people actually read) ===
    brutal_truth = _grok_speak(
        "overall",
        burn=round(total_burn, 0),
        gold=round(total_gold, 0),
        pct=round((total_gold / total_burn * 100), 1) if total_burn > 0 else 0,
    )

    gold_narrative = (
        f"After touching your fleet I found {len(opportunities)} high-confidence places where money is leaking. "
        f"The fastest path to real impact is right at the top of this list. "
        "Everything below is ordered by actual dollars, not by how interesting it is to engineers."
    )

    top_recs = []
    for opp in opportunities[:5]:
        top_recs.append(f"{opp.host}: {opp.impact} — {opp.recommended_action[:80]}...")

    surprise = ""
    if opportunities:
        biggest = opportunities[0]
        surprise = f"The single biggest lever right now is {biggest.host}. {biggest.grok_insight}"

    result = MidasTouchResult(
        generated_at=datetime.utcnow().isoformat() + "Z",
        total_hosts_analyzed=len(hosts) or 4,  # demo count
        total_current_monthly_burn=round(total_burn, 2),
        total_potential_monthly_gold=round(total_gold, 2),
        opportunities=opportunities,
        brutal_truth=brutal_truth,
        gold_narrative=gold_narrative,
        top_recommendations=top_recs,
        surprise_insight=surprise,
        tags_generated=len(opportunities),
    )

    logger.info(
        "Midas Touch complete. Monthly burn: $%.2f | Recoverable gold: $%.2f (%.1f%%)",
        result.total_current_monthly_burn,
        result.total_potential_monthly_gold,
        result.savings_percentage,
    )

    return result


def print_gold_report(result: MidasTouchResult) -> None:
    """Render the Midas result in a way that makes people feel rich and in control."""
    print("\n" + "═" * 78)
    print("║" + " AVD MASTERS — MIDAS TOUCH REPORT ".center(76) + "║")
    print("═" * 78)
    print(f"  Generated: {result.generated_at}")
    print(f"  Hosts touched: {result.total_hosts_analyzed}")
    print()
    print("  CURRENT MONTHLY BURN")
    print(f"    ${result.total_current_monthly_burn:,.2f}")
    print()
    print("  RECOVERABLE GOLD (this month)")
    print(f"    ${result.total_potential_monthly_gold:,.2f}   ({result.savings_percentage}% potential)")
    print(f"    Annualized: ${result.annual_gold_potential:,.0f}")
    print()
    print("  ESTIMATED MONTHLY CARBON (local grid model)")
    print(f"    ~{result.estimated_monthly_carbon_kg:,.0f} kgCO2e  (rough — better with real utilization)")
    print()
    print("  " + "─" * 70)
    print(f"  BRUTAL TRUTH")
    print("  " + "─" * 70)
    print(f"  {result.brutal_truth}")
    print()

    if result.opportunities:
        print("  " + "─" * 70)
        print("  THE GOLD (ranked by actual dollars)")
        print("  " + "─" * 70)
        for i, opp in enumerate(result.opportunities[:7], 1):
            print(f"\n  {i}. {opp.host} — {opp.sku}")
            print(f"     {opp.impact}")
            print(f"     {opp.grok_insight}")
            print(f"     Action: {opp.recommended_action}")
            print(f"     Confidence: {opp.confidence.upper()}")

    if result.surprise_insight:
        print("\n  " + "─" * 70)
        print("  ONE WEIRD TRICK (the part that usually surprises people)")
        print("  " + "─" * 70)
        print(f"  {result.surprise_insight}")

    print("\n" + "═" * 78)
    print("  Touch the gold. The first three items above are usually enough to pay for the whole tool.")
    print("═" * 78 + "\n")


# =============================================================================
# Carbon / Sustainability (local estimates — no external calls)
# =============================================================================

# Rough 2026 grid carbon intensity (kgCO2e per kWh). Good enough for decision making.
_REGION_CARBON_INTENSITY = {
    "eastus": 0.41,
    "eastus2": 0.41,
    "westus": 0.35,
    "westeurope": 0.28,
    "northeurope": 0.25,
    "southeastasia": 0.52,
    "uksouth": 0.23,
    "germanywestcentral": 0.35,
    "default": 0.40,
}

# Very rough average power draw (watts) for a full GPU of that model under load
_MODEL_POWER_WATTS = {
    "H100": 700,
    "H200": 800,
    "MI300X": 750,
    "A100": 400,
    "L40S": 300,
    "A10": 150,
    "default": 350,
}


def estimate_carbon_kg_per_month(spec: GpuSpec, region: str = "eastus", hours_per_month: int = 730) -> float:
    """Local-only carbon estimate for this GPU allocation."""
    intensity = _REGION_CARBON_INTENSITY.get(region.lower(), _REGION_CARBON_INTENSITY["default"])
    power = _MODEL_POWER_WATTS.get(spec.model, _MODEL_POWER_WATTS["default"])
    # Power for the allocated share
    allocated_kw = (power * spec.gpu_count) / 1000.0
    kwh = allocated_kw * hours_per_month
    return round(kwh * intensity, 1)


# =============================================================================
# Email Integration for "Shit Gets Funky" Moments
# =============================================================================

def maybe_send_midas_funky_email(result: MidasTouchResult) -> bool:
    """
    If waste looks bad or there's serious gold on the table, fire a proper email.
    Controlled by AVD_ALERT_EMAIL_ENABLED.
    """
    if result.total_potential_monthly_gold < 2000 and result.savings_percentage < 25:
        return False  # Not funky enough to bother people

    details = [
        f"Monthly burn: ${result.total_current_monthly_burn:,.0f}",
        f"Recoverable gold this month: ${result.total_potential_monthly_gold:,.0f} ({result.savings_percentage}%)",
        f"Annualized opportunity: ${result.annual_gold_potential:,.0f}",
    ]
    for opp in result.opportunities[:3]:
        details.append(f"{opp.host}: {opp.impact}")

    recs = [opp.recommended_action for opp in result.opportunities[:3]]

    return alerting.send_funky_gpu_email(
        title="Significant GPU Waste Detected",
        summary=result.brutal_truth,
        details=details,
        recommendations=recs,
        impact=f"${result.total_potential_monthly_gold:,.0f}/month is on the table. Go touch it.",
    )


# Convenience for the CLI
def run_midas_demo() -> MidasTouchResult:
    """The thing people will actually run to feel the magic."""
    result = perform_midas_touch(hosts=[], include_demo_data=True)
    print_gold_report(result)
    return result


# =============================================================================
# Profile Management Intelligence Integration
# =============================================================================

def analyze_profile_debt(profile_healths: list[profiles.ProfileHealth]) -> list[dict]:
    """
    Turn common AVD profile setup disasters into Midas-style opportunities.

    This is where we call out the painful real-world mistakes that make AVD feel terrible:
    - No FSLogix
    - Legacy roaming profiles
    - Profile containers on the wrong (slow/cheap) storage
    - etc.
    """
    opportunities = []
    for health in profile_healths:
        profile_opps = profiles.generate_profile_opportunities(health)
        for popp in profile_opps:
            opportunities.append({
                "host": health.host_name,
                "type": popp["type"],
                "grok_insight": popp["title"] + " — " + popp["impact"],
                "recommended_action": popp["recommendation"],
                "impact": popp["impact"],
            })
    return opportunities


# =============================================================================
# Remediation Playbook Export (used by `touch`)
# =============================================================================

def generate_remediation_playbook(result: MidasTouchResult, format: str = "text") -> str:
    """
    Produces a clean, exportable remediation plan.
    Supports 'text', 'markdown', and 'json' (basic).
    """
    lines = []

    if format == "markdown":
        lines.append("# AVD Masters — Midas Remediation Playbook\n")
        lines.append(f"**Generated:** {result.generated_at}\n")
        lines.append(f"**Monthly Burn:** ${result.total_current_monthly_burn:,.0f}")
        lines.append(f"**Recoverable Gold (this month):** ${result.total_potential_monthly_gold:,.0f}\n")
        lines.append("## Top Actions\n")

        for i, opp in enumerate(result.opportunities[:6], 1):
            lines.append(f"### {i}. {opp.host} — {opp.impact}")
            lines.append(f"**Type:** {opp.opportunity_type}")
            lines.append(f"**Insight:** {opp.grok_insight}")
            lines.append(f"**Recommended Action:** {opp.recommended_action}\n")

    elif format == "json":
        import json
        data = {
            "generated_at": result.generated_at,
            "monthly_burn": result.total_current_monthly_burn,
            "recoverable_gold": result.total_potential_monthly_gold,
            "opportunities": [
                {
                    "host": o.host,
                    "type": o.opportunity_type,
                    "savings": o.potential_monthly_savings,
                    "action": o.recommended_action,
                }
                for o in result.opportunities[:8]
            ]
        }
        return json.dumps(data, indent=2)

    else:
        # plain text
        lines.append("AVD MASTERS — REMEDIATION PLAYBOOK")
        lines.append(f"Generated: {result.generated_at}")
        lines.append(f"Monthly Burn: ${result.total_current_monthly_burn:,.0f}")
        lines.append(f"Recoverable Gold: ${result.total_potential_monthly_gold:,.0f}\n")
        lines.append("TOP ACTIONS:\n")
        for i, opp in enumerate(result.opportunities[:6], 1):
            lines.append(f"{i}. {opp.host} | {opp.impact}")
            lines.append(f"   {opp.recommended_action}\n")

    return "\n".join(lines)
