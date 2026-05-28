"""Tests for the Workspace Facts API (Story HF.1).

Covers: models, store CRUD, REST endpoints, MCP tool wiring, error handling.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest


class TestKnowledgeModels:
    """Verify model shapes match the shared contract v1."""

    @pytest.fixture
    def source(self):
        def _make(type="manual_admin", id=None, observed_at=None):
            from llm_wiki.knowledge.models import KnowledgeSource

            return KnowledgeSource(type=type, id=id, observed_at=observed_at)

        return _make

    @pytest.fixture
    def fact(self, source):
        def _make(**kwargs):
            defaults = {
                "workspace_id": "test-ws",
                "category": "workspace.roster",
                "key": "test.key",
                "value": {"name": "test"},
                "source": source(type="manual_admin"),
                "created_at": datetime.now(tz=UTC),
                "updated_at": datetime.now(tz=UTC),
                "version": 1,
            }
            defaults.update(kwargs)
            from llm_wiki.knowledge.models import KnowledgeFact

            return KnowledgeFact(**defaults)

        return _make

    def test_fact_serializes_json(self, fact):
        f = fact()
        data = f.model_dump()
        assert data["workspace_id"] == "test-ws"
        assert data["category"] == "workspace.roster"
        assert data["version"] == 1
        # UUID is preserved as UUID in model_dump without json strategy

    def test_fact_defaults(self, source):
        from llm_wiki.knowledge.models import KnowledgeFact

        f = KnowledgeFact(
            workspace_id="ws",
            category="workspace.roster",
            key="k",
            value={},
            source=source(),
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
            version=1,
        )
        assert f.status == "active"
        assert f.visibility == "workspace"
        assert f.provenance == []

    def test_write_request_fields(self):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest, KnowledgeSource

        req = KnowledgeFactWriteRequest(
            category="workspace.roster",
            key="test.key",
            value={"a": 1},
            source=KnowledgeSource(type="manual_admin"),
        )
        assert req.category == "workspace.roster"
        assert req.expected_previous_version is None

    def test_write_response_status_variants(self):
        from llm_wiki.knowledge.models import KnowledgeFactWriteResponse

        valid = {"written", "unchanged", "stale_rejected", "pending_review", "conflict_detected"}
        for status in valid:
            resp = KnowledgeFactWriteResponse(key="k", status=status)
            assert resp.status == status

    def test_list_response_structure(self):
        from llm_wiki.knowledge.models import KnowledgeListResponse

        resp = KnowledgeListResponse()
        assert resp.facts == []
        assert resp.next_cursor is None
        assert resp.total_hint == 0

    def test_conflict_model(self):
        from llm_wiki.knowledge.models import KnowledgeConflict

        c = KnowledgeConflict(key="k", candidates=[])
        assert c.requires_review is True

    def test_response_status_invariants(self):
        from llm_wiki.knowledge.models import KnowledgeFactWriteResponse

        # written requires fact — allowed by schema but validator notes it
        resp = KnowledgeFactWriteResponse(key="k", status="written")
        assert resp.status == "written"
        assert resp.fact is None


class TestCategoryValidation:
    """Category normalization and alias handling."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    def test_valid_categories_accepted(self, store):
        for cat in [
            "workspace.roster",
            "workspace.pets",
            "workspace.schedule",
            "workspace.rooms",
        ]:
            store._normalize_category(cat)

    def test_aliases_resolve_to_canonical(self, store):
        assert store._normalize_category("household.roster") == "workspace.roster"
        assert store._normalize_category("household.pets") == "workspace.pets"
        assert store._normalize_category("household.schedule") == "workspace.schedule"

    def test_invalid_category_raises(self, store):
        from llm_wiki.exceptions import UnknownFactCategoryError

        with pytest.raises(UnknownFactCategoryError, match="not a recognized knowledge category"):
            store._normalize_category("workspace.dishes")

    def test_unknown_alias_raises(self, store):
        from llm_wiki.exceptions import UnknownFactCategoryError

        with pytest.raises(UnknownFactCategoryError, match="not a recognized knowledge category"):
            store._normalize_category("household.frogs")


class TestFactStoreCRUD:
    """Core CRUD operations using real file I/O in temp dirs."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    @pytest.fixture
    def source(self):
        from llm_wiki.knowledge.models import KnowledgeSource

        return lambda **kw: KnowledgeSource(type="manual_admin", **kw)

    def test_put_and_get_fact(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        req = KnowledgeFactWriteRequest(
            category="workspace.roster",
            key="household.members.bob",
            value={"name": "Bob", "role": "adult"},
            source=source(),
        )
        result = store.put_fact(ws, req)
        assert result.status == "written"
        assert result.fact is not None
        assert result.fact.workspace_id == ws

        fact = store.get_fact(ws, "household.members.bob")
        assert fact is not None
        assert fact.value == {"name": "Bob", "role": "adult"}
        assert fact.version == 1

    def test_put_returns_unchanged_for_same_value(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        key = "test.key"
        req = KnowledgeFactWriteRequest(
            category="workspace.roster",
            key=key,
            value={"same": True},
            source=source(),
        )
        store.put_fact(ws, req)
        result = store.put_fact(ws, req)
        assert result.status == "unchanged"

    def test_put_returns_stale_rejected_on_version_mismatch(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        key = "test.key"

        store.put_fact(
            ws,
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key=key,
                value={"v": 1},
                source=source(),
            ),
        )
        result = store.put_fact(
            ws,
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key=key,
                value={"v": 99},
                source=source(),
                expected_previous_version=99,
            ),
        )
        assert result.status == "stale_rejected"

    def test_version_monotonicity(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        key = "test.versioned"

        for i in range(1, 6):
            result = store.put_fact(
                ws,
                KnowledgeFactWriteRequest(
                    category="workspace.roster",
                    key=key,
                    value={"seq": i},
                    source=source(),
                ),
            )
            assert result.fact is not None
            assert result.fact.version == i

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_fact("nonexistent", "key") is None

    def test_delete_tombstoned(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        key = "test.delete"
        store.put_fact(
            ws,
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key=key,
                value={"age": 5},
                source=source(),
            ),
        )

        result = store.delete_fact(ws, key)
        assert result is not None
        assert result.status == "deleted"
        assert result.version == 2

        fact = store.get_fact(ws, key)
        assert fact is None, "Fact should be invisible after deletion"

    def test_delete_nonexistent_returns_none(self, store):
        assert store.delete_fact("ws", "key") is None

    def test_list_facts_empty(self, store):
        result = store.list_facts("ws")
        assert result.facts == []
        assert result.total_hint == 0

    def test_list_facts_populated(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        store.put_fact(
            ws,
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key="a",
                value={"x": 1},
                source=source(),
            ),
        )
        store.put_fact(
            ws,
            KnowledgeFactWriteRequest(
                category="workspace.pets",
                key="b",
                value={"y": 2},
                source=source(),
            ),
        )

        all_facts = store.list_facts(ws)
        assert all_facts.total_hint == 2

        roster = store.list_facts(ws, category="workspace.roster")
        assert roster.total_hint == 1
        assert roster.facts[0].key == "a"

    def test_list_pagination(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        for i in range(5):
            store.put_fact(
                ws,
                KnowledgeFactWriteRequest(
                    category="workspace.roster",
                    key=f"key.{i}",
                    value={"i": i},
                    source=source(),
                ),
            )

        page1 = store.list_facts(ws, limit=2)
        assert len(page1.facts) == 2
        assert page1.next_cursor is not None

        page2 = store.list_facts(ws, limit=2, cursor=page1.next_cursor)
        assert len(page2.facts) == 2

    def test_batch_put(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        reqs = [
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key=f"batch.{i}",
                value={"n": i},
                source=source(),
            )
            for i in range(3)
        ]
        results = store.batch_put(ws, reqs)
        assert len(results) == 3
        assert all(r.status == "written" for r in results)

        for i, r in enumerate(results):
            assert r.fact is not None
            assert r.fact.value == {"n": i}

    def test_get_history_returns_all_versions(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        ws = "house-1"
        key = "test.history"

        for v in range(1, 4):
            store.put_fact(
                ws,
                KnowledgeFactWriteRequest(
                    category="workspace.roster",
                    key=key,
                    value={"v": v},
                    source=source(),
                ),
            )

        history = store.get_history(ws, key)
        assert len(history) == 3

    def test_jsonl_well_formed(self, store):
        """Each JSONL line in history should be independently parseable."""
        from llm_wiki.knowledge.models import (
            KnowledgeFactWriteRequest,
            KnowledgeSource,
        )

        ws = "house-1"
        key = "test.jsonl"

        for i in range(3):
            store.put_fact(
                ws,
                KnowledgeFactWriteRequest(
                    category="workspace.roster",
                    key=key,
                    value={"i": i},
                    source=KnowledgeSource(type="manual_admin"),
                ),
            )

        # Read the actual JSONL file
        hist_path = store._history_path(ws, key)
        assert hist_path.exists()

        lines = [line for line in hist_path.read_text().splitlines() if line.strip()]
        assert len(lines) == 3
        for line in lines:
            data = json.loads(line)
            assert data["key"] == key

    def test_workspace_initialization(self, store):
        ws = "new-workspace"
        facts_path = store._ensure_workspace(ws)
        store._ensure_workspace(ws)  # idempotent
        assert facts_path.exists()
        assert facts_path.is_dir()


class TestWorkspaceScoping:
    """Verify workspace isolation."""

    @pytest.fixture
    def store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    @pytest.fixture
    def source(self):
        from llm_wiki.knowledge.models import KnowledgeSource

        return lambda **kw: KnowledgeSource(type="manual_admin", **kw)

    def test_facts_are_workspace_scoped(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        store.put_fact(
            "ws-a",
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key="same.key",
                value={"ws": "a"},
                source=source(),
            ),
        )

        assert store.get_fact("ws-b", "same.key") is None

    def test_different_values_same_key_different_workspaces(self, store, source):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        store.put_fact(
            "ws-a",
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key="shared.key",
                value={"ws": "a"},
                source=source(),
            ),
        )
        store.put_fact(
            "ws-b",
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key="shared.key",
                value={"ws": "b"},
                source=source(),
            ),
        )

        assert store.get_fact("ws-a", "shared.key").value == {"ws": "a"}
        assert store.get_fact("ws-b", "shared.key").value == {"ws": "b"}


class TestRouteIntegration:
    """Integration tests for REST endpoints."""

    @pytest.fixture
    def knowledge_store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    @pytest.fixture
    def app(self, knowledge_store):
        from fastapi import FastAPI

        from llm_wiki.api.routers.facts import router as facts_router

        app = FastAPI()
        app.include_router(facts_router)
        app.state.knowledge_store = knowledge_store
        return app

    @pytest.fixture
    def source(self):
        from llm_wiki.knowledge.models import KnowledgeSource

        return lambda **kw: KnowledgeSource(type=kw.pop("type", "manual_admin"), **kw)

    @pytest.mark.asyncio
    async def test_get_fact_404(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/v1/workspaces/ws1/facts/nonexistent")
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_fact_200(self, app, knowledge_store, source):
        from httpx import ASGITransport, AsyncClient

        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        knowledge_store.put_fact(
            "ws1",
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key="test.key",
                value={"x": 1},
                source=source(),
            ),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/v1/workspaces/ws1/facts/test.key")
            assert response.status_code == 200
            data = response.json()
            assert data["key"] == "test.key"
            assert data["value"] == {"x": 1}
            assert data["version"] == 1

    @pytest.mark.asyncio
    async def test_put_fact(self, app, knowledge_store, source):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.put(
                "/v1/workspaces/ws1/facts/test.key",
                json={
                    "category": "workspace.roster",
                    "key": "test.key",
                    "value": {"name": "test"},
                    "source": {"type": "manual_admin"},
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "written"
            assert data["fact"]["version"] == 1

    @pytest.mark.asyncio
    async def test_unknown_category_returns_422(self, app, knowledge_store):
        """AC: 11 — UnknownFactCategoryError → HTTP 422 with details."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.put(
                "/v1/workspaces/ws1/facts/test.key",
                json={
                    "category": "workspace.dishes",
                    "key": "test.key",
                    "value": {"x": 1},
                    "source": {"type": "manual_admin"},
                },
            )
            assert response.status_code == 422
            data = response.json()
            detail = data.get("detail", {})
            assert detail.get("error_code") == "UNKNOWN_KNOWLEDGE_CATEGORY"
            details = detail.get("details", {})
            assert details.get("category") == "workspace.dishes"
            assert "workspace.dishes" not in details.get("valid_categories", [])

    @pytest.mark.asyncio
    async def test_delete_fact(self, app, knowledge_store, source):
        from httpx import ASGITransport, AsyncClient

        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        knowledge_store.put_fact(
            "ws1",
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key="to.delete",
                value={"x": 1},
                source=source(),
            ),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete("/v1/workspaces/ws1/facts/to.delete")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "deleted"
            assert data["version"] == 2

    @pytest.mark.asyncio
    async def test_list_facts(self, app, knowledge_store, source):
        from httpx import ASGITransport, AsyncClient

        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        knowledge_store.put_fact(
            "ws1",
            KnowledgeFactWriteRequest(
                category="workspace.roster",
                key="a",
                value={"x": 1},
                source=source(),
            ),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/v1/workspaces/ws1/facts")
            assert response.status_code == 200
            data = response.json()
            assert data["total_hint"] == 1

    @pytest.mark.asyncio
    async def test_batch_put(self, app, knowledge_store):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/v1/workspaces/ws1/facts:batch",
                json=[
                    {
                        "category": "workspace.roster",
                        "key": "batch.1",
                        "value": {"n": 1},
                        "source": {"type": "manual_admin"},
                    },
                    {
                        "category": "workspace.roster",
                        "key": "batch.2",
                        "value": {"n": 2},
                        "source": {"type": "manual_admin"},
                    },
                ],
            )
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert all(r["status"] == "written" for r in data)

    @pytest.mark.asyncio
    async def test_fact_history(self, app, knowledge_store, source):
        from httpx import ASGITransport, AsyncClient

        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest

        for v in range(1, 3):
            knowledge_store.put_fact(
                "ws1",
                KnowledgeFactWriteRequest(
                    category="workspace.roster",
                    key="history.key",
                    value={"v": v},
                    source=source(),
                ),
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/v1/workspaces/ws1/facts/history.key/history")
            assert response.status_code == 200
            history = response.json()
            assert len(history) == 2


class TestMCPToolWiring:
    """Verify MCP tools register and call the right service methods."""

    @pytest.fixture
    def mock_wiki(self, temp_dir: Path):
        from types import SimpleNamespace

        return SimpleNamespace(wiki_base=Path(temp_dir))

    @pytest.fixture
    def knowledge_store(self, temp_dir: Path):
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        return WorkspaceFactStore(wiki_base=str(temp_dir))

    @pytest.fixture
    def mock_server(self):
        class MockServer:
            tools = []

            def tool(self, *a, **kw):
                def decorator(func):
                    self.tools.append(func)
                    return func

                return decorator

        return MockServer()

    def test_tools_register_with_store(self, mock_server, mock_wiki, knowledge_store):
        from llm_wiki.mcp.tools import register_tools

        register_tools(
            mock_server,
            mock_wiki,
            knowledge_store=knowledge_store,
        )
        tool_names = [t.__name__ for t in mock_server.tools]
        for name in [
            "fact_get",
            "fact_list",
            "fact_put",
            "fact_delete",
            "fact_history",
            "fact_batch_put",
        ]:
            assert name in tool_names, f"Expected {name} in registered tools"

    def test_tools_not_registered_without_store(self, mock_server, mock_wiki):
        from llm_wiki.mcp.tools import register_tools

        register_tools(mock_server, mock_wiki, knowledge_store=None)
        tool_names = [t.__name__ for t in mock_server.tools]
        assert "fact_get" not in tool_names
