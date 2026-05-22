"""Pydantic response models for per-domain dashboards (Story 3-5)."""

from __future__ import annotations

from pydantic import BaseModel


class ConfidenceDistribution(BaseModel):
    """Histogram of page confidence scores in buckets."""

    low: int = 0  # 0.0–0.3
    medium: int = 0  # 0.3–0.6
    high: int = 0  # 0.6–1.0


class RecentChange(BaseModel):
    """A single recent change entry."""

    id: str
    page_id: str
    timestamp: str
    change_type: str
    actor: str


class LastGovernanceRun(BaseModel):
    """Summary of the last governance job completion."""

    last_run: str | None = None
    outcome: str = "unknown"
    warnings: int = 0


class DashboardResponse(BaseModel):
    """Dashboard data for a single domain."""

    domain: str
    page_count: int
    confidence_distribution: ConfidenceDistribution
    low_confidence_count: int = 0
    stale_count: int = 0
    recent_changes: list[RecentChange] = []
    last_governance_run: LastGovernanceRun | None = None


class DashboardListResponse(BaseModel):
    """List of dashboard responses for all domains."""

    domains: list[DashboardResponse]
