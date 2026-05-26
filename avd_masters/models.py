"""
AVD Masters — Core Data Models

These models are the contract between collection, analysis, storage, and the API.

They are deliberately simple, strongly typed, and built to last.
No magic. No 47-field god objects. Just the right shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

from avd_masters.types import Vendor, HostStatus, ImbalanceLabel

# Optional forward reference for cost data
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from avd_masters.cost import CostSummary


# =============================================================================
# Raw Hardware Samples
# =============================================================================

class GpuSample(BaseModel):
    """
    One GPU's raw reading at a point in time.

    This is as close as we get to the metal without being on the box.
    Everything else in the system is derived from collections of these.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    timestamp: datetime
    host_name: str

    sku: Optional[str] = None
    vendor: Vendor

    gpu_index: int
    gpu_name: Optional[str] = None
    gpu_uuid: Optional[str] = None

    gpu_util_pct: Optional[float] = Field(default=None, ge=0, le=100)
    mem_util_pct: Optional[float] = Field(default=None, ge=0, le=100)

    mem_total_mb: Optional[float] = None
    mem_used_mb: Optional[float] = None

    temp_c: Optional[float] = None
    power_w: Optional[float] = None
    pstate: Optional[str] = None


class SessionSample(BaseModel):
    """Best-effort concurrent session count on a host."""

    model_config = ConfigDict(extra="ignore")

    timestamp: datetime
    host_name: str
    active_sessions: int = 0
    disconnected_sessions: int = 0


# =============================================================================
# Enriched Views (what humans and dashboards actually care about)
# =============================================================================

class HostGpu(BaseModel):
    """Single GPU as presented in the enriched host view."""

    index: int
    name: Optional[str] = None
    uuid: Optional[str] = None
    util_pct: Optional[float] = None
    mem_used_mb: Optional[float] = None
    mem_total_mb: Optional[float] = None
    mem_util_pct: Optional[float] = None
    temp_c: Optional[float] = None
    power_w: Optional[float] = None
    pstate: Optional[str] = None


class HostStatusModel(BaseModel):
    """
    The enriched, analyzed picture of one AVD session host.

    This is what the imbalance engine, UI, and API consumers work with.
    """

    model_config = ConfigDict(extra="ignore")

    host_name: str
    address: str

    sku: Optional[str] = None
    vendor: Optional[Vendor] = None
    gpu_count: float = 0.0
    vram_mb: int = 0
    retiring: bool = False

    status: HostStatus = "unknown"
    last_seen: Optional[datetime] = None

    gpu_util_avg_pct: Optional[float] = None
    mem_used_avg_pct: Optional[float] = None
    temp_avg_c: Optional[float] = None
    power_total_w: Optional[float] = None

    active_sessions: int = 0
    sessions_per_gpu: Optional[float] = None

    gpus: list[HostGpu] = Field(default_factory=list)

    # FinOps / Cost fields (populated by avd_masters.cost)
    estimated_hourly_cost_usd: Optional[float] = None
    total_gpu_seconds: float = 0.0
    estimated_cost_usd: Optional[float] = None
    cost_tags: dict[str, str] = Field(default_factory=dict)


class PoolAnalysis(BaseModel):
    """
    The complete pool-level view.

    This is the primary thing the dashboard (and any external system) consumes.
    It tells the real story of balance, pressure, and risk.
    """

    model_config = ConfigDict(extra="ignore")

    timestamp: datetime

    host_count: int
    online_count: int
    total_gpu_count: float

    pool_util_mean_pct: Optional[float] = None
    pool_util_stddev_pct: Optional[float] = None
    pool_mem_mean_pct: Optional[float] = None

    imbalance_score: float = 0.0
    imbalance_label: ImbalanceLabel = "balanced"

    overloaded_hosts: list[str] = Field(default_factory=list)
    heavy_hosts: list[str] = Field(default_factory=list)

    hosts: list[HostStatusModel] = Field(default_factory=list)

    # Aggregated FinOps metrics
    total_estimated_cost_usd: Optional[float] = None
    total_gpu_seconds: float = 0.0
    cost_by_model: dict[str, float] = Field(default_factory=dict)  # e.g. {"H100": 124.50}


# =============================================================================
# Collector & Discovery Contracts
# =============================================================================

class CollectorResult(BaseModel):
    """What any collector (WinRM, SSH, future) must return."""

    model_config = ConfigDict(extra="ignore")

    host_name: str
    timestamp: datetime
    gpu_samples: list[GpuSample] = Field(default_factory=list)
    session_sample: Optional[SessionSample] = None
    error: Optional[str] = None
    vendor: Optional[Vendor] = None
    sku: Optional[str] = None


class DiscoveredHost(BaseModel):
    """Host discovered via Azure AVD APIs."""

    model_config = ConfigDict(extra="ignore")

    name: str
    address: str
    subscription_id: str
    resource_group: str
    host_pool: str
    vm_size: Optional[str] = None
    status: str = "Unknown"
    gpu_spec: Optional[dict] = None
