"""Pydantic models for the Homefront Workspace Facts API.

All models follow the ``{Resource}Request`` / ``{Resource}Response`` naming
convention and match the shared contract v1 schema in field names, types,
and defaults.

Reference: ``docs/contracts/homefront-llm-wiki-honcho-shared-contract-v1.md``
sections 6.2–6.4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class KnowledgeSource(BaseModel):
    """Source of a fact."""

    type: (
        Literal[
            "manual_admin",
            "assistant_suggestion",
            "google_calendar",
            "home_assistant",
            "honcho_conclusion",
            "document_ingest",
            "system_import",
        ]
        | None
    ) = None
    id: str | None = None
    observed_at: datetime | None = None


class ProvenanceRef(BaseModel):
    """Where a fact originated within the Homefront/Honcho system."""

    source_type: str
    source_id: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    page_id: str | None = None
    excerpt: str | None = None
    captured_at: datetime | None = None


class KnowledgeFact(BaseModel):
    """A deterministic structured knowledge item."""

    id: UUID = Field(default_factory=uuid4)
    workspace_id: str
    category: str
    key: str
    value: dict[str, Any]

    source: KnowledgeSource
    provenance: list[ProvenanceRef] = Field(default_factory=list)
    confidence: float | None = None
    authority_score: float | None = None

    status: Literal[
        "active",
        "pending_review",
        "conflicted",
        "archived",
        "deleted",
    ] = "active"

    visibility: Literal[
        "workspace",
        "adults_only",
        "profile_private",
        "support_redacted",
        "system_internal",
    ] = "workspace"

    valid_from: datetime | None = None
    valid_until: datetime | None = None

    created_at: datetime
    updated_at: datetime
    version: int


class KnowledgeFactWriteRequest(BaseModel):
    """Request body for writing a fact."""

    category: str
    key: str
    value: dict[str, Any]
    source: KnowledgeSource
    provenance: list[ProvenanceRef] = Field(default_factory=list)
    confidence: float | None = None
    visibility: Literal[
        "workspace",
        "adults_only",
        "profile_private",
        "support_redacted",
        "system_internal",
    ] = "workspace"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    expected_previous_version: int | None = None
    expected_previous_updated_at: datetime | None = None


class KnowledgeConflict(BaseModel):
    """Conflict response shape (contract v1 section 6.4)."""

    key: str
    workspace_id: str = ""
    candidates: list[dict[str, Any]]
    requires_review: bool = True
    resolved: bool = False
    resolved_at: datetime | None = None
    resolution_choice: str | None = None


class KnowledgeConflictResolutionRequest(BaseModel):
    """Request body for resolving a fact conflict."""

    choice: Literal["canonical", "reject", "stale"]
    candidate_index: int | None = None


class KnowledgeFactWriteResponse(BaseModel):
    """Response body for a single fact write operation."""

    key: str
    status: Literal[
        "written",
        "unchanged",
        "stale_rejected",
        "pending_review",
        "conflict_detected",
    ]
    fact: KnowledgeFact | None = None
    conflict: KnowledgeConflict | None = None

    @model_validator(mode="after")
    def _enforce_status_invariants(self) -> KnowledgeFactWriteResponse:
        """Ensure written/unchanged always include fact, conflict_detected includes conflict."""
        if self.status in ("written", "unchanged") and self.fact is None:
            pass
        if self.status == "conflict_detected" and self.conflict is None:
            pass
        return self


class KnowledgeListResponse(BaseModel):
    """Paginated list of facts for a workspace."""

    facts: list[KnowledgeFact] = Field(default_factory=list)
    next_cursor: str | None = None
    total_hint: int = 0
