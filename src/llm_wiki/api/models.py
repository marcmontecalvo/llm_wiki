"""API Pydantic models.

All models follow the ``{Resource}Request`` / ``{Resource}Response`` naming
convention — never ``Schema``, ``Model``, or ``Out``.  Stub models are
included for endpoints that will be populated in later stories.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response body."""

    error_code: str
    message: str
    rebuild_hint: bool = False


class HealthResponse(BaseModel):
    """Health check response."""

    running: bool
    config_dir: str
    daemon_running: bool = False


class DaemonStatusResponse(BaseModel):
    """Daemon status (stub — populated in Story 1.6)."""

    running: bool


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


class IngestRequest(BaseModel):
    """Ingest request body (stub — populated in Story 1.6)."""

    file_path: str


class IngestStatusResponse(BaseModel):
    """Ingest status response (stub — populated in Story 1.6)."""

    status: str = "queued"
    path: str = ""


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
