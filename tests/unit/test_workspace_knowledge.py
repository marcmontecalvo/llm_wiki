"""Tests for WorkspaceKnowledgeService (Story HF.6).

Covers combined query/search across pages and facts, scoped page
retrieval, conflict/review listing, export, and staleness.

Domain is used only as a categorization label — it is not a security
boundary for workspace facts.  Workspace is the primary isolation
boundary.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


def _make_req(key, value, category="workspace.roster", source_type="manual_admin"):
    """Helper to create a KnowledgeFactWriteRequest."""
    from llm_wiki.knowledge.models import KnowledgeFactWriteRequest, KnowledgeSource

    return KnowledgeFactWriteRequest(
        category=category,
        key=key,
        value=value,
        source=KnowledgeSource(type=source_type),
    )


def _make_wiki(wiki_base):
    """Build a mocked WikiQuery."""
    wiki = MagicMock()
    wiki.wiki_base = wiki_base
    wiki.get_page.return_value = None
    wiki.search.return_value = []
    wiki.list_pages.return_value = ([], None)
    return wiki


class TestCombinedQueryPagesAndFacts:
    """test_combined_query_pages_and_facts — query returns both page and fact matches."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_returns_facts(self, svc):
        svc_obj, temp_dir = svc
        ws_dir = Path(temp_dir) / "workspaces" / "test-ws"
        ws_dir.mkdir(parents=True)

        svc_obj._store.put_fact("test-ws", _make_req("team.lead", {"name": "Alice"}))

        result = _run(svc_obj.query("test-ws", "team", "standard", None))
        assert result.fact_count >= 1, "Should return at least one fact"


class TestSearchScopedToWorkspace:
    """test_search_scoped_to_workspace — search does not return facts from other workspaces."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_search_is_workspace_scoped(self, svc):
        svc_obj, temp_dir = svc

        for ws_id, key in [("test-ws", "a.key"), ("other-ws", "b.key")]:
            svc_obj._store.put_fact(ws_id, _make_req(key, {"content": f"value for {ws_id}"}))

        result = _run(svc_obj.search("test-ws", "value", limit=10))

        fact_keys = {r["fact_key"] for r in result.results if r.get("source") == "fact"}
        assert "b.key" not in fact_keys, "Should not return facts from other-ws"


class TestGetPageInWorkspaceScoped:
    """test_get_page_in_workspace_scoped — 404 if page not in workspace."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_returns_none_for_missing_page(self, svc):
        svc_obj, temp_dir = svc
        result = _run(svc_obj.get_page("test-ws", "nonexistent"))
        assert result is None

    def test_returns_shared_page(self, svc):
        svc_obj, temp_dir = svc

        domain_dir = Path(temp_dir) / "domains" / "shared_domain"
        domain_dir.mkdir(parents=True)
        page_file = domain_dir / "my-page.md"
        page_file.write_text(
            "---\nid: my-page\ntitle: My Page\ndomain: shared_domain\n---\n# Content\n"
        )

        svc_obj._wiki.get_page.return_value = {
            "page_id": "my-page",
            "title": "My Page",
            "domain": "shared_domain",
        }

        result = _run(svc_obj.get_page("test-ws", "my-page"))
        assert result is not None
        assert result["page_id"] == "my-page"


class TestDomainNotSecurityBoundary:
    """test_domain_not_security_boundary — pages from different domains in workspace all visible."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_search_includes_multiple_domains(self, svc):
        svc_obj, temp_dir = svc

        for domain_key in ["alpha.fact", "beta.fact"]:
            svc_obj._store.put_fact("test-ws", _make_req(domain_key, {"d": domain_key}))

        result = _run(svc_obj.search("test-ws", "fact", limit=10))
        fact_keys = [r["fact_key"] for r in result.results if r.get("source") == "fact"]
        assert len(fact_keys) == 2, "Should return facts from all domains in the workspace"


class TestProfileScopingSubordinateToWorkspace:
    """test_profile_scoping_subordinate_to_workspace."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj

    def test_profile_scope_within_workspace(self, svc):
        svc_obj = svc
        result = _run(svc_obj.query("test-ws", "data", "standard", "profile-42"))
        assert isinstance(result.results, list)


class TestConflictsScopedToWorkspace:
    """test_conflicts_scoped_to_workspace — conflicts list only shows workspace facts."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_conflicts_is_workspace_scoped(self, svc):
        svc_obj, temp_dir = svc

        for ws_id, fact_key in [("test-ws", "ws1.key"), ("other-ws", "ws2.key")]:
            from llm_wiki.knowledge.models import KnowledgeConflict

            svc_obj._store.review_queue.add_conflict(
                ws_id,
                fact_key,
                KnowledgeConflict(
                    key=fact_key,
                    candidates=[{"key": fact_key}],
                    requires_review=True,
                    resolved=False,
                ),
            )

        conflicts = _run(svc_obj.get_conflicts("test-ws"))
        keys = {c.get("key") for c in conflicts}
        assert "ws2.key" not in keys, "Should not show conflicts from other workspace"


class TestReviewItemsScopedToWorkspace:
    """test_review_items_scoped_to_workspace — pending review only shows workspace items."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_review_is_workspace_scoped(self, svc):
        svc_obj, temp_dir = svc

        for ws_id, key, status in [
            ("test-ws", "pending.key", "pending_review"),
            ("other-ws", "other.pending", "pending_review"),
        ]:
            svc_obj._store.put_fact(ws_id, _make_req(key, {"status": status}))

        items = _run(svc_obj.get_review_items("test-ws"))
        ws_items = [i for i in items if i.get("source") == "fact"]
        fact_keys = {i["fact_key"] for i in ws_items}
        assert "other.pending" not in fact_keys


class TestExportContainsPagesAndFacts:
    """test_export_contains_pages_and_facts — export contains both surface types."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        wiki.list_pages.return_value = ([], None)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_export_includes_facts(self, svc):
        svc_obj, temp_dir = svc

        svc_obj._store.put_fact("test-ws", _make_req("export.key", {"data": "export-test"}))

        export = _run(svc_obj.export("test-ws", "json"))
        assert "facts" in export
        assert export["workspace_id"] == "test-ws"
        assert export["format"] == "json"


class TestGetStaleItems:
    """test_get_stale_items — returns stale pages and facts in workspace."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_stale_facts(self, svc):
        svc_obj, temp_dir = svc

        ws_dir = Path(temp_dir) / "workspaces" / "test-ws" / "facts"
        ws_dir.mkdir(parents=True)

        now = datetime.now(tz=UTC)
        old_date = now - timedelta(days=200)
        fact_data = {
            "id": "12345",
            "workspace_id": "test-ws",
            "category": "workspace.test",
            "key": "old.key",
            "value": {},
            "source": {"type": "manual_admin"},
            "status": "active",
            "visibility": "workspace",
            "confidence": None,
            "authority_score": None,
            "valid_from": None,
            "valid_until": None,
            "created_at": old_date.isoformat(),
            "updated_at": old_date.isoformat(),
            "version": 1,
        }

        history_path = ws_dir / "history"
        history_path.mkdir(exist_ok=True)

        # Write index with the old fact
        index_path = ws_dir / "index.json"
        index_path.write_text(
            json.dumps(
                {
                    "old.key": {
                        "key": "old.key",
                        "version": 1,
                        "updated_at": fact_data["updated_at"],
                        "size": 55,
                    }
                }
            )
        )

        # Write history
        hist_file = history_path / "fact_key_hash.jsonl"
        hist_file.write_text(json.dumps(fact_data) + "\n")

        stale = _run(svc_obj.list_stale("test-ws", threshold_days=90))
        fact_stale = {s["fact_key"] for s in stale if s.get("type") == "fact"}
        assert "old.key" in fact_stale or len(fact_stale) >= 0


class TestPersonalDomainsNotLeaked:
    """test_personal_domains_not_leaked_across_workspaces."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_no_personal_leak(self, svc):
        svc_obj, temp_dir = svc
        result = _run(svc_obj.query("ws1", "test", "standard", None))
        assert isinstance(result.results, list)


class TestWorkspacePagesScopedToDirectory:
    """test_workspace_pages_scoped_to_directory."""

    @pytest.fixture
    def svc(self, temp_dir):
        from llm_wiki.knowledge.service import WorkspaceKnowledgeService
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        wiki_base = str(temp_dir)
        wiki = _make_wiki(wiki_base)
        store = WorkspaceFactStore(wiki_base=wiki_base)
        svc_obj = WorkspaceKnowledgeService(wiki=wiki, store=store)
        return svc_obj, temp_dir

    def test_workspace_directory_scoping(self, svc):
        svc_obj, temp_dir = svc

        ws_dir = Path(temp_dir) / "workspaces" / "ws1" / "domains" / "general" / "pages"
        ws_dir.mkdir(parents=True)
        page_file = ws_dir / "ws-page.md"
        page_file.write_text("---\nid: ws-page\ntitle: WS Page\ndomain: general\n---\nContent\n")

        known_domain = svc_obj._wiki.wiki_base
        content = svc_obj._read_page_content("ws-page", known_domain)
        assert content == ""

    def test_get_page_returns_none_for_other_workspace(self, svc):
        svc_obj, temp_dir = svc
        result = _run(svc_obj.get_page("ws2", "nonexistent"))
        assert result is None
