"""Tests for the Homefront export/delete endpoints (Story HF.7).

Covers: workspace fact export, profile-scoped export, schema version,
provenance reconstruction, tombstone-profile-delete, error handling on
corrupt data, and full export bundle structure.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from llm_wiki.knowledge.export import (
    SCHEMA_VERSION,
    export_facts,
    tombstone_profile_facts,
)
from llm_wiki.knowledge.models import (
    KnowledgeFact,
    KnowledgeSource,
    ProvenanceRef,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


def _fact(**kwargs) -> KnowledgeFact:
    """Create a minimal KnowledgeFact for testing."""
    now = datetime(2026, 5, 1, tzinfo=UTC)
    defaults: dict = {
        "workspace_id": "ws1",
        "category": "general.test",
        "key": "test.key",
        "value": {"data": "example"},
        "source": KnowledgeSource(),
        "provenance": [],
        "status": "active",
        "visibility": "workspace",
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }
    defaults.update(kwargs)
    return KnowledgeFact(**defaults)


def _provenance(source_type="honcho_conclusion", source_id=None):
    return [
        ProvenanceRef(
            source_type=source_type,
            source_id=source_id,
            captured_at=datetime.now(tz=UTC),
        )
    ]


class TestWorkspaceExport:
    """AC: 1 — workspace-level export returns all active facts."""

    def test_export_workspace_returns_all_active_facts(self):
        """No profile_id → all active workspace-scoped facts."""
        facts = [
            _fact(visibility="workspace", key="a", value={"x": 1}),
            _fact(visibility="workspace", key="b", value={"x": 2}),
            _fact(visibility="profile_private", key="c", value={"x": 3}),
        ]

        result = export_facts(
            list_facts_fn=lambda wid: facts,
            get_fact_fn=lambda wid, k: None,
            workspace_id="ws1",
        )

        assert len(result["facts"]) == 2  # only workspace-scoped
        assert {f["key"] for f in result["facts"]} == {"a", "b"}

    def test_empty_workspace(self):
        """No facts → returns empty bundle, not None."""
        result = export_facts(
            list_facts_fn=lambda wid: [],
            get_fact_fn=lambda wid, k: None,
            workspace_id="ws1",
        )
        assert result["facts"] == []
        assert result["provenance"] == []

    def test_response_contains_workspace_id(self):
        assert (
            export_facts(
                list_facts_fn=lambda wid: [],
                get_fact_fn=lambda wid, k: None,
                workspace_id="any-workspace",
            )["workspace_id"]
            == "any-workspace"
        )


class TestProfileScopedExport:
    """AC: 2, 3 — profile-scoped export and schema version."""

    def test_export_with_profile_id_returns_only_matching_private(self):
        """profile_id → only profile-private facts matching that profile."""
        facts = [
            _fact(
                visibility="profile_private",
                key="priv1",
                provenance=_provenance(source_id="profile-abc"),
            ),
            _fact(
                visibility="profile_private",
                key="priv2",
                provenance=_provenance(source_id="profile-xyz"),
            ),
            _fact(
                visibility="workspace",
                key="shared",
            ),
        ]

        result = export_facts(
            list_facts_fn=lambda wid: facts,
            get_fact_fn=lambda wid, k: None,
            workspace_id="ws1",
            profile_id="profile-abc",
        )

        assert len(result["facts"]) == 1
        assert result["facts"][0]["key"] == "priv1"

    def test_export_profile_id_wrong_match_returns_empty(self):
        """Non-matching profile_id → empty facts list."""
        facts = [
            _fact(
                visibility="profile_private",
                key="priv1",
                provenance=_provenance(source_id="profile-abc"),
            ),
        ]
        result = export_facts(
            list_facts_fn=lambda wid: facts,
            get_fact_fn=lambda wid, k: None,
            workspace_id="ws1",
            profile_id="nonexistent",
        )
        assert result["facts"] == []

    def test_export_includes_schema_version(self):
        result = export_facts(
            list_facts_fn=lambda wid: [],
            get_fact_fn=lambda wid, k: None,
            workspace_id="ws1",
        )
        assert result["schema_version"] == SCHEMA_VERSION

    def test_export_includes_provenance(self):
        facts = [
            _fact(
                visibility="workspace",
                key="f1",
                provenance=_provenance(source_type="test", source_id="sid-1"),
            ),
        ]
        result = export_facts(
            list_facts_fn=lambda wid: facts,
            get_fact_fn=lambda wid, k: None,
            workspace_id="ws1",
        )
        assert len(result["provenance"]) == 1
        assert result["provenance"][0]["source_type"] == "test"

    def test_export_includes_each_fact_provenance(self):
        """Each fact entry must carry its provenance list."""
        facts = [
            _fact(
                visibility="workspace",
                key="f1",
                provenance=_provenance(source_type="desc", source_id="source-1"),
            ),
        ]
        result = export_facts(
            list_facts_fn=lambda wid: facts,
            get_fact_fn=lambda wid, k: None,
            workspace_id="ws1",
        )
        fact = result["facts"][0]
        assert "provenance" in fact
        assert len(fact["provenance"]) == 1

    def test_profile_match_via_value(self):
        """A fact with profile_id in value dict should match."""
        facts = [
            _fact(
                visibility="profile_private",
                key="v1",
                value={"owner": "profile-abc", "other": "data"},
                provenance=_provenance(source_id="different-source"),
            ),
        ]
        # _fact_matches_profile is tested via tombstone below
        # since it's internal; verify it works by matching via tombstone
        mock_store = MagicMock()
        mock_store.list_all_facts.return_value = facts
        mock_store._get_workspace_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_store._get_workspace_lock.return_value.__exit__ = MagicMock(return_value=None)

        tombstone_profile_facts(mock_store, "ws1", "profile-abc")

        assert mock_store.delete_fact.call_count == 1
        assert mock_store.delete_fact.call_args[0][1] == "v1"


class TestTombstoneProfileFacts:
    """AC: 4 — tombstone only profile-private facts for given profile."""

    def test_tombstone_profile_private_facts_only(self):
        """Tombstone should not touch visibility=workspace facts."""
        private_fact = _fact(
            visibility="profile_private",
            key="p1",
            provenance=_provenance(source_id="profile-abc"),
        )
        workspace_fact = _fact(
            visibility="workspace",
            key="w1",
            value={"data": "different"},
        )

        mock_store = MagicMock()
        mock_store.list_all_facts.return_value = [private_fact, workspace_fact]
        mock_store._get_workspace_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_store._get_workspace_lock.return_value.__exit__ = MagicMock(return_value=None)

        count = tombstone_profile_facts(mock_store, "ws1", "profile-abc")

        assert count == 1
        # delete_fact should be called only once (for the private fact)
        mock_store.delete_fact.assert_called_once_with("ws1", "p1")

    def test_tombstone_returns_count(self):
        private1 = _fact(
            visibility="profile_private", key="p1", provenance=_provenance(source_id="pid")
        )
        private2 = _fact(
            visibility="profile_private", key="p2", provenance=_provenance(source_id="pid")
        )

        mock_store = MagicMock()
        mock_store.list_all_facts.return_value = [private1, private2]
        mock_store._get_workspace_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_store._get_workspace_lock.return_value.__exit__ = MagicMock(return_value=None)

        count = tombstone_profile_facts(mock_store, "ws1", "pid")

        assert count == 2
        assert mock_store.delete_fact.call_count == 2

    def test_no_matching_facts(self):
        private_fact = _fact(
            visibility="profile_private", key="p1", provenance=_provenance(source_id="other")
        )

        mock_store = MagicMock()
        mock_store.list_all_facts.return_value = [private_fact]
        mock_store._get_workspace_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_store._get_workspace_lock.return_value.__exit__ = MagicMock(return_value=None)

        count = tombstone_profile_facts(mock_store, "ws1", "nonexistent")

        assert count == 0
        mock_store.delete_fact.assert_not_called()


class TestErrorCodeOnCorrupt:
    """AC: 5 — corrupt data returns 503 with FACT_EXPORT_FAILED."""

    def test_error_on_corrupt_data(self):
        """Store raises → RuntimeError → FactExportFailed → 503."""
        err = RuntimeError("IOError: corrupt index")

        def export_fn(*a, **kw):
            raise err

        with pytest.raises(RuntimeError, match="FACT_EXPORT_FAILED"):
            export_facts(
                list_facts_fn=export_fn,
                get_fact_fn=lambda wid, k: None,
                workspace_id="ws1",
            )


class TestExportBundleStructure:
    """AC: 6 — export bundle contains all expected top-level keys."""

    def test_full_homefront_export_bundle_structure(self):
        """Top-level response has all keys per contract v1 section 9.1."""
        result = export_facts(
            list_facts_fn=lambda wid: [_fact(visibility="workspace", key="f1")],
            get_fact_fn=lambda wid, k: None,
            workspace_id="ws1",
        )
        assert "schema_version" in result
        assert "workspace_id" in result
        assert "generated_at" in result
        assert "facts" in result
        assert "provenance" in result
        assert result["schema_version"] == "homefront-export-v1"


class TestDeeplyNestedValueStep:
    """Verify iterative BFS handles deeply nested structures without recursion depth error."""

    def test_deeply_nested_dict_value(self):
        """A fact with deeply nested value should match via iterative search."""
        deep_value: dict = {"a": {"b": {"c": {"d": "target-profile"}}}}
        fact = _fact(
            visibility="profile_private",
            key="deep",
            value=deep_value,
            provenance=_provenance(source_id="different-source"),
        )
        mock_store = MagicMock()
        mock_store.list_all_facts.return_value = [fact]
        mock_store._get_workspace_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_store._get_workspace_lock.return_value.__exit__ = MagicMock(return_value=None)

        count = tombstone_profile_facts(mock_store, "ws1", "target-profile")

        assert count == 1

    def test_deeply_nested_list_value(self):
        """A fact with deeply nested list containing profile should match."""
        fact = _fact(
            visibility="profile_private",
            key="deep",
            value={"items": [[["target-profile"]]]},
            provenance=(),
        )
        mock_store = MagicMock()
        mock_store.list_all_facts.return_value = [fact]
        mock_store._get_workspace_lock.return_value.__enter__ = MagicMock(return_value=None)
        mock_store._get_workspace_lock.return_value.__exit__ = MagicMock(return_value=None)

        count = tombstone_profile_facts(mock_store, "ws1", "target-profile")

        assert count == 1
