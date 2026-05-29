"""Workspace fact export and profile-scoped delete service.

Supports Homefront's privacy contract: structured fact export and
profile-privacy-compliant tombstoning (delete-by-profile).

Reference: shared contract v1 section 9.1.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from llm_wiki.knowledge.models import KnowledgeFact

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "homefront-export-v1"


def _fact_matches_profile(fact: KnowledgeFact, profile_id: str) -> bool:
    """Return True if a fact belongs to the given profile_id.

    A fact matches when any provenance ref has source_id == profile_id,
    or when the fact value contains a dict key whose value is the profile_id.

    Uses iterative BFS to avoid unbounded recursion on deeply nested values.
    """
    for ref in fact.provenance:
        if ref.source_id == profile_id:
            return True

    # Iterative BFS over nested value structure
    stack = list(fact.value.values()) if isinstance(fact.value, dict) else [fact.value]
    while stack:
        v = stack.pop()
        if v == profile_id:
            return True
        if isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
    return False


def _build_provenance_list(facts: list[KnowledgeFact]) -> list[dict[str, Any]]:
    """Collect unique provenance refs across all exported facts."""
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    refs: list[dict[str, Any]] = []
    for fact in facts:
        for ref in fact.provenance:
            key = (ref.source_type, ref.source_id, ref.session_id, ref.message_id)
            if key not in seen:
                seen.add(key)
                refs.append(ref.model_dump())
    return refs


def export_facts(
    list_facts_fn: Callable[[str], list[KnowledgeFact]],
    get_fact_fn: Callable[[str, str], KnowledgeFact | None],
    workspace_id: str,
    *,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Export facts for a workspace.

    Args:
        list_facts_fn: Callable(workspace_id) -> list[KnowledgeFact]
        get_fact_fn: Callable(workspace_id, fact_key) -> KnowledgeFact | None
        workspace_id: Target workspace.
        profile_id: Optional profile to scope the export.

    Returns:
        Dict matching the homefront-export-v1 schema:
        {schema_version, workspace_id, generated_at, facts, provenance}

    Raises:
        RuntimeError: If the store cannot be read (corrupt data).
    """
    try:
        all_facts: list[KnowledgeFact] = list_facts_fn(workspace_id)
    except Exception as e:
        logger.error("Failed to list facts for workspace %s: %s", workspace_id, e)
        raise RuntimeError(f"FACT_EXPORT_FAILED: Cannot read fact store: {e}") from e

    if not all_facts:
        return {
            "schema_version": SCHEMA_VERSION,
            "workspace_id": workspace_id,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "facts": [],
            "provenance": [],
        }

    if profile_id:
        filtered: list[KnowledgeFact] = [
            f
            for f in all_facts
            if f.visibility == "profile_private" and _fact_matches_profile(f, profile_id)
        ]
    else:
        filtered = [f for f in all_facts if f.visibility == "workspace"]

    provenance = _build_provenance_list(filtered)
    return {
        "schema_version": SCHEMA_VERSION,
        "workspace_id": workspace_id,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "facts": [f.model_dump() for f in filtered],
        "provenance": provenance,
    }


def tombstone_profile_facts(
    store: Any,
    workspace_id: str,
    profile_id: str,
) -> int:
    """Tombstone all profile-private facts for a given profile.

    Acquires the workspace write lock to prevent races between listing
    and deleting. Only facts with ``visibility == "profile_private"``
    whose profile_id matches (via provenance or fact value) are affected.
    Workspace-scoped facts are untouched.

    Args:
        store: WorkspaceFactStore instance.
        workspace_id: Target workspace.
        profile_id: Profile to remove facts for.

    Returns:
        Count of tombstoned facts.
    """
    ws_lock = store._get_workspace_lock(workspace_id)
    count = 0

    with ws_lock:
        all_facts: list[KnowledgeFact] = store.list_all_facts(workspace_id)
        for fact in all_facts:
            if fact.visibility != "profile_private":
                continue
            if not _fact_matches_profile(fact, profile_id):
                continue
            store.delete_fact(workspace_id, fact.key)
            count += 1
    return count
