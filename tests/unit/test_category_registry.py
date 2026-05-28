"""Tests for the category registry module (Story HF.3).

Covers: canonical acceptance, alias normalization, unknown category errors,
REST endpoint, MCP tool, CLI command, and stability properties.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CANONICAL_LIST = [
    "workspace.roster",
    "workspace.assignments",
    "workspace.pets",
    "workspace.appliances",
    "workspace.preferences",
    "workspace.schedule",
    "workspace.vehicles",
    "workspace.presence",
    "workspace.recurring_responsibilities",
    "workspace.rooms",
    "workspace.integrations",
    "workspace.voice_nodes",
]

ALIAS_MAP = {
    "household.roster": "workspace.roster",
    "household.assignments": "workspace.assignments",
    "household.pets": "workspace.pets",
    "household.appliances": "workspace.appliances",
    "household.preferences": "workspace.preferences",
    "household.schedule": "workspace.schedule",
    "household.vehicles": "workspace.vehicles",
    "household.presence": "workspace.presence",
    "household.recurring_responsibilities": "workspace.recurring_responsibilities",
}
CANONICAL_Sorted = sorted(CANONICAL_LIST)


class TestCanonicalCategories:
    """AC: 1 — canonical workspace.* names accepted as-is."""

    def test_all_canonical_names_accepted(self):
        from llm_wiki.knowledge.categories import normalize_category

        for cat in CANONICAL_LIST:
            assert normalize_category(cat) == cat

    def test_canonical_frozenset_has_all_items(self):
        from llm_wiki.knowledge.categories import CANONICAL_CATEGORIES

        for cat in CANONICAL_LIST:
            assert cat in CANONICAL_CATEGORIES
        assert len(CANONICAL_CATEGORIES) == len(CANONICAL_LIST)


class TestAliases:
    """AC: 2 — household.* aliases resolve to workspace.*."""

    def test_each_alias_resolves(self):
        from llm_wiki.knowledge.categories import CATEGORY_ALIASES, normalize_category

        for raw, expected in ALIAS_MAP.items():
            assert CATEGORY_ALIASES[raw] == expected
            assert normalize_category(raw) == expected

    def test_non_alias_canonical_is_stable(self):
        from llm_wiki.knowledge.categories import normalize_category

        for cat in CANONICAL_LIST:
            assert normalize_category(cat) == cat


class TestUnknownCategoryError:
    """AC: 6 — unknown categories raise UnknownFactCategoryError."""

    def test_unknown_category_raises(self):
        from llm_wiki.exceptions import UnknownFactCategoryError
        from llm_wiki.knowledge.categories import normalize_category

        with pytest.raises(UnknownFactCategoryError, match="not a recognized knowledge category"):
            normalize_category("workspace.dishes")

    def test_unknown_alias_raises(self):
        from llm_wiki.exceptions import UnknownFactCategoryError
        from llm_wiki.knowledge.categories import normalize_category

        with pytest.raises(UnknownFactCategoryError, match="not a recognized knowledge category"):
            normalize_category("household.frogs")

    def test_error_has_valid_categories(self):
        from llm_wiki.exceptions import UnknownFactCategoryError

        try:
            raise UnknownFactCategoryError("workspace.nonexistent", sorted(CANONICAL_LIST))
        except UnknownFactCategoryError as exc:
            assert exc.category == "workspace.nonexistent"
            assert "workspace.nonexistent" not in exc.valid_categories
            assert len(exc.valid_categories) > 0

    def test_error_valid_categories_sorted(self):
        from llm_wiki.exceptions import UnknownFactCategoryError

        try:
            raise UnknownFactCategoryError("bad", ["zzz", "aaa", "mmm"])
        except UnknownFactCategoryError as exc:
            assert exc.valid_categories == sorted(["zzz", "aaa", "mmm"])


class TestNormalizationStability:
    """Normalize is idempotent and deterministic."""

    def test_normalize_normalize_stable(self):
        from llm_wiki.knowledge.categories import normalize_category

        for cat in CANONICAL_LIST:
            result = normalize_category(normalize_category(cat))
            assert result == normalize_category(cat)

        for alias in ALIAS_MAP:
            first = normalize_category(alias)
            second = normalize_category(first)
            assert first == second

    def test_case_sensitivity(self):
        from llm_wiki.knowledge.categories import normalize_category

        """Registered forms are exact match — case variants must fail."""
        with pytest.raises(Exception, match="not a recognized knowledge category"):
            normalize_category("Workspace.Pets")

        with pytest.raises(Exception, match="not a recognized knowledge category"):
            normalize_category("WORKSPACE.ROSTER")

        with pytest.raises(Exception, match="not a recognized knowledge category"):
            normalize_category("household.Roster")


class TestIsValidCategory:
    """AC: 1 — fast is_valid_category check."""

    def test_valid_canonical(self):
        from llm_wiki.knowledge.categories import is_valid_category

        for cat in CANONICAL_LIST:
            assert is_valid_category(cat) is True

    def test_aliases_not_valid(self):
        from llm_wiki.knowledge.categories import is_valid_category

        # Aliases are NOT in the canonical set — only normalize_category accepts them
        for alpha in ALIAS_MAP:
            assert is_valid_category(alpha) is False

    def test_unknown(self):
        from llm_wiki.knowledge.categories import is_valid_category

        assert is_valid_category("workspace.nonexistent") is False
        assert is_valid_category("random.nonsense") is False


class TestCategoriesList:
    """AC: 3 — get_categories_list returns correct structure."""

    def test_returns_canonical_and_aliases(self):
        from llm_wiki.knowledge.categories import get_categories_list

        data = get_categories_list()
        assert "canonical" in data
        assert "aliases" in data

    def test_canonical_is_sorted_list(self):
        from llm_wiki.knowledge.categories import get_categories_list

        data = get_categories_list()
        assert data["canonical"] == sorted(CANONICAL_LIST)

    def test_aliases_are_mapping(self):
        from llm_wiki.knowledge.categories import get_categories_list

        data = get_categories_list()
        for alias, canonical in data["aliases"].items():
            assert alias in ALIAS_MAP
            assert canonical == ALIAS_MAP[alias]


# ── REST endpoint tests ────────────────────────────────────────────────────


class TestCategoryEndpoint:
    """AC: 3 — REST endpoint returns registry."""

    @pytest.fixture
    def app(self, temp_dir: Path):
        from fastapi import FastAPI

        from llm_wiki.api.routers.facts import router as facts_router
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        app = FastAPI()
        app.include_router(facts_router)
        app.state.knowledge_store = WorkspaceFactStore(wiki_base=str(temp_dir))
        return app

    @pytest.mark.asyncio
    async def test_categories_endpoint_structure(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/v1/workspaces/ws1/facts/categories")
            assert response.status_code == 200
            data = response.json()
            assert "canonical" in data
            assert "aliases" in data
            assert len(data["canonical"]) == len(CANONICAL_LIST)
            assert len(data["aliases"]) == len(ALIAS_MAP)

    @pytest.mark.asyncio
    async def test_categories_served_for_any_workspace(self, app):
        """Same data for all workspaces (global registry)."""
        from httpx import ASGITransport, AsyncClient

        for ws in ["ws-a", "ws-b", "any-workspace"]:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                response = await c.get(f"/v1/workspaces/{ws}/facts/categories")
                assert response.status_code == 200
                data = response.json()
                assert len(data["canonical"]) == len(CANONICAL_Sorted)

    @pytest.mark.asyncio
    async def test_canonical_field_is_list(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/v1/workspaces/ws1/facts/categories")
            data = response.json()
            assert isinstance(data["canonical"], list)
            assert sorted(data["canonical"]) == CANONICAL_Sorted

    @pytest.mark.asyncio
    async def test_aliases_field_is_object(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/v1/workspaces/ws1/facts/categories")
            data = response.json()
            assert isinstance(data["aliases"], dict)
            for k, v in data["aliases"].items():
                assert k in ALIAS_MAP
                assert v == ALIAS_MAP[k]


# ── MCP tool tests ─────────────────────────────────────────────────────────


class TestMCPCategoriesTool:
    """AC: 4 — MCP categories_list tool returns same data as REST."""

    @pytest.fixture
    def mock_wiki(self, temp_dir: Path):
        from types import SimpleNamespace

        return SimpleNamespace(wiki_base=Path(temp_dir))

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

    def test_categories_list_tool_exists(self, mock_server, mock_wiki):
        from llm_wiki.mcp.tools import register_tools

        register_tools(mock_server, mock_wiki, knowledge_store=None)
        tool_names = [t.__name__ for t in mock_server.tools]
        assert "categories_list" in tool_names

    def test_categories_list_returns_correct_data(self, mock_server, mock_wiki):
        from llm_wiki.mcp.tools import register_tools

        register_tools(mock_server, mock_wiki, knowledge_store=None)
        tool_fn = None
        for t in mock_server.tools:
            if t.__name__ == "categories_list":
                tool_fn = t
                break

        assert tool_fn is not None
        result = tool_fn()
        assert "canonical" in result
        assert "aliases" in result
        assert sorted(result["canonical"]) == CANONICAL_Sorted


class TestRESTAndMCPParity:
    """REST and MCP serve the same data."""

    @pytest.fixture
    def mock_wiki(self, temp_dir: Path):
        from types import SimpleNamespace

        return SimpleNamespace(wiki_base=Path(temp_dir))

    @pytest.fixture
    def mock_server(self, mock_wiki):

        class MockServer:
            tools = []

            def tool(self, *a, **kw):
                def decorator(func):
                    self.tools.append(func)
                    return func

                return decorator

        return MockServer()

    def test_mcp_and_rest_data_identical(self, mock_server, mock_wiki, temp_dir: Path):
        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        from llm_wiki.api.routers.facts import router as facts_router
        from llm_wiki.knowledge.storage import WorkspaceFactStore
        from llm_wiki.mcp.tools import register_tools

        # Get MCP data
        register_tools(mock_server, mock_wiki, knowledge_store=None)
        tool_fn = next(t for t in mock_server.tools if t.__name__ == "categories_list")
        mcp_data = tool_fn()

        # Get REST data
        app = FastAPI()
        app.include_router(facts_router)
        app.state.knowledge_store = WorkspaceFactStore(wiki_base=str(temp_dir))

        async def compare():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/v1/workspaces/ws1/facts/categories")
                return resp.json()

        import asyncio

        rest_data = asyncio.get_event_loop().run_until_complete(compare())

        assert mcp_data == rest_data


# ── CLI tests ──────────────────────────────────────────────────────────────


class TestCLICategoriesCommand:
    """AC: 5 — CLI prints category registry."""

    def test_facts_categories_exists(self):
        """The 'facts' CLI group and 'categories' command should be registered."""
        from click.testing import CliRunner

        from llm_wiki.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["facts", "categories"])
        assert result.exit_code == 0, result.output

    def test_facts_categories_default_output(self):
        from click.testing import CliRunner

        from llm_wiki.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["facts", "categories"])
        assert result.exit_code == 0
        assert (
            "names" in result.output.lower()
            or "workspace" in result.output.lower()
            or "roster" in result.output
        )

    def test_facts_categories_json_output(self):
        from click.testing import CliRunner

        from llm_wiki.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["facts", "categories", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "canonical" in data
        assert "aliases" in data
        assert len(data["canonical"]) == len(CANONICAL_LIST)

    def test_facts_categories_json_has_all_canonical(self):
        from click.testing import CliRunner

        from llm_wiki.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["facts", "categories", "--json"])
        data = json.loads(result.output)
        assert sorted(data["canonical"]) == CANONICAL_Sorted


# ── batch_put alias normalization ────────────────────────────────────────


class TestBatchPutNormalization:
    """AC: 7 — batch_put normalizes aliases to canonical form."""

    def test_batch_put_normalizes_household_alias(self, temp_dir: Path):
        from llm_wiki.knowledge.models import KnowledgeFactWriteRequest, KnowledgeSource
        from llm_wiki.knowledge.storage import WorkspaceFactStore

        store = WorkspaceFactStore(wiki_base=str(temp_dir))
        req = KnowledgeFactWriteRequest(
            key="test-alias-batch",
            category="household.roster",
            value={"info": "test"},
            source=KnowledgeSource(system="presidio", version="0.1"),
        )
        results = store.batch_put("ws1", [req])
        assert len(results) == 1
        assert results[0].status == "written"
        assert results[0].fact is not None
        assert results[0].fact.category == "workspace.roster"
