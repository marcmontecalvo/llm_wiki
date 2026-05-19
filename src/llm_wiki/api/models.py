"""API Pydantic models.

All models follow the ``{Resource}Request`` / ``{Resource}Response`` naming
convention — never ``Schema``, ``Model``, or ``Out``.
"""

from __future__ import annotations

from typing import Any

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
    """Query request body."""

    query: str
    depth: str = Field(default="quick")
    domain: str | None = None


class QueryResponse(BaseModel):
    """Query response body."""

    results: list[Any] = Field(default_factory=list)
    timed_out: bool = False
    partial: bool = False
    vector_search: bool = False


class SearchResponse(BaseModel):
    """Search response (stub — populated in Story 1.7)."""

    results: list[Any] = Field(default_factory=list)


class PageResponse(BaseModel):
    """Single page response (stub)."""

    id: str = ""
    title: str = ""
    domain: str = ""
    kind: str = ""
    tags: list[str] = Field(default_factory=list)


class PageListResponse(BaseModel):
    """Paginated page list (stub)."""

    pages: list[PageResponse] = Field(default_factory=list)
    total: int = 0


class ExportResponse(BaseModel):
    """Export response (stub — populated in Story 1.7)."""

    export_id: str = ""
    status: str = "pending"
    download_url: str | None = None
