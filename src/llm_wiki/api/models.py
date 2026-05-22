"""API Pydantic models.

All models follow the ``{Resource}Request`` / ``{Resource}Response`` naming
convention — never ``Schema``, ``Model``, or ``Out``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error_code: str
    message: str
    rebuild_hint: bool = False


# ── Story 1.6 ──────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    """Health check response."""

    daemon_running: bool
    index_loaded: bool
    scheduler_state: str
    llm_extraction_enabled: bool
    query_log_ok: bool = True


class JobStatus(BaseModel):
    """Single daemon job status for daemon/status endpoint."""

    job_name: str
    last_run: str | None = None
    next_run: str | None = None
    last_result: str | None = None
    status: str = "unknown"


class DaemonStatusResponse(BaseModel):
    """Daemon status — list of all registered jobs with schedule info."""

    jobs: list[JobStatus] = Field(default_factory=list)


class IngestRequest(BaseModel):
    """Ingest request body.

    Provide either ``source_path`` (file to ingest) or ``content`` (markdown text),
    optionally scoped to a domain.
    """

    source_path: str | None = None
    content: str | None = None
    domain: str | None = None


class IngestStatusResponse(BaseModel):
    """Ingest job status response."""

    job_id: str
    status: str
    source_path: str | None = None
    domain: str | None = None
    page_ids: list[str] = Field(default_factory=list)
    indexed: bool = False
    message: str | None = None


class DomainInfo(BaseModel):
    """Single domain with metadata."""

    name: str
    scope: str
    page_count: int = 0
    last_updated: str | None = None


class DomainListResponse(BaseModel):
    """List of configured domains with metadata."""

    domains: list[DomainInfo] = Field(default_factory=list)


# ── Story 1.4 / 1.7 stubs ─────────────────────────────────────────────────────


class QueryRequest(BaseModel):
    """Query request body.

    ``depth`` controls synchronicity: ``quick``/``standard`` run
    synchronously; ``deep`` dispatches to a background task and
    returns 202 Accepted immediately.
    """

    query: str
    depth: Literal["quick", "standard", "deep"] = Field(default="quick")
    domain: str | None = None


class QueryResultItem(BaseModel):
    """Single result inside a query response."""

    page_id: str
    title: str
    confidence: float = 0.0
    provenance: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    authority_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Authority score from backlink analysis"
    )


class QueryResponse(BaseModel):
    """Query response body.

    ``job_id`` / ``status`` are populated only for deep-query submissions
    (202 response).  ``results`` is populated for quick/standard sync
    responses and for completed deep-query polls.
    """

    results: list[QueryResultItem] = Field(default_factory=list)
    timed_out: bool = False
    partial: bool = False
    was_heuristic: bool = False
    job_id: str | None = None
    status: str | None = None


class SearchResultItem(BaseModel):
    """Single result from the search endpoint."""

    page_id: str
    title: str
    confidence: float = 0.0
    score: float = 0.0


class SearchResponse(BaseModel):
    """Search response — always merges full-text and vector results."""

    results: list[SearchResultItem] = Field(default_factory=list)


class PageResponse(BaseModel):
    """Single page response — full content plus frontmatter."""

    page_id: str
    title: str
    content: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    domain: str = ""
    kind: str = ""
    confidence: float = 0.0
    authority_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Authority score from backlink analysis"
    )


class PageListResponse(BaseModel):
    """Paginated page list from MetadataIndex."""

    pages: list[PageResponse] = Field(default_factory=list)
    next_cursor: str | None = None
    total_hint: int = 0


class ExportResponse(BaseModel):
    """Export response — serves exported file content."""

    format: str
    content: str
    generated_at: datetime | None = None
    page_count: int = 0


# ── Story 3.5: Per-Domain Dashboards ───────────────────────────────────────────


class DashboardConfidenceDistribution(BaseModel):
    """Histogram of page confidence scores in buckets."""

    low: int = 0  # 0.0–0.3
    medium: int = 0  # 0.3–0.6
    high: int = 0  # 0.6–1.0


class DashboardRecentChange(BaseModel):
    """A single recent change entry."""

    id: str
    page_id: str
    timestamp: str
    change_type: str
    actor: str


class DashboardLastGovernanceRun(BaseModel):
    """Summary of last governance job completion."""

    last_run: str | None = None
    outcome: str = "unknown"
    warnings: int = 0


class DashboardResponse(BaseModel):
    """Dashboard data for a single domain."""

    domain: str
    page_count: int
    confidence_distribution: DashboardConfidenceDistribution
    low_confidence_count: int = 0
    stale_count: int = 0
    recent_changes: list[DashboardRecentChange] = Field(default_factory=list)
    last_governance_run: DashboardLastGovernanceRun | None = None


class DashboardListResponse(BaseModel):
    """List of dashboard responses for all domains."""

    domains: list[DashboardResponse] = Field(default_factory=list)
