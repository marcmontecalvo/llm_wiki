"""Tests for multi-user domain scoping (Story 1.9).

Covers DomainConfig scope/field validation, WikiQuery domain resolution,
and the search integration.
"""

import pytest
from pydantic import ValidationError

from llm_wiki.models.config import DomainConfig, DomainsYAML
from llm_wiki.query.search import WikiQuery


class TestDomainConfigScoping:
    """Tests for DomainConfig scope and owner fields."""

    def test_scope_defaults_to_shared(self):
        """AC 1: scope defaults to 'shared' when omitted."""
        d = DomainConfig(id="test", title="T", description="D")
        assert d.scope == "shared"

    def test_personal_scope_requires_owner(self):
        """AC 2: scope='personal' with no owner raises ValidationError."""
        with pytest.raises(ValidationError):
            DomainConfig(id="test", title="T", description="D", scope="personal")

    def test_personal_scope_with_owner_valid(self):
        """AC 2: scope='personal' with owner is valid."""
        d = DomainConfig(
            id="user-marc", title="Marc", description="Marc's", scope="personal", owner="marc"
        )
        assert d.scope == "personal"
        assert d.owner == "marc"

    def test_shared_domain_with_no_owner_valid(self):
        """AC 3: shared domains with no owner are valid."""
        d = DomainConfig(
            id="household", title="Household", description="Shared", scope="shared", owner=None
        )
        assert d.scope == "shared"
        assert d.owner is None

    def test_owner_coerces_empty_string_to_none(self):
        """Edge case: empty string owner is coerced to None."""
        d = DomainConfig(id="test", title="T", description="D", owner="")
        assert d.owner is None


class TestResolveSearchDomains:
    """Tests for WikiQuery._resolve_search_domains method."""

    @pytest.fixture
    def domains_config(self) -> DomainsYAML:
        """Create domain config with shared and personal domains."""
        return DomainsYAML.model_validate(
            {
                "domains": [
                    {
                        "id": "household",
                        "title": "Household",
                        "description": "Shared",
                        "scope": "shared",
                    },
                    {
                        "id": "general",
                        "title": "General",
                        "description": "General",
                        "scope": "shared",
                    },
                    {
                        "id": "user-marc",
                        "title": "Marc",
                        "description": "Personal",
                        "scope": "personal",
                        "owner": "marc",
                    },
                    {
                        "id": "user-alice",
                        "title": "Alice",
                        "description": "Personal",
                        "scope": "personal",
                        "owner": "alice",
                    },
                ]
            }
        )

    @pytest.fixture
    def wiki_with_config(self, temp_dir, domains_config):
        """Create WikiQuery with domains config and some indexed pages."""
        wiki_base = temp_dir / "wiki"
        wiki_base.mkdir()
        domains_dir = wiki_base / "domains"
        for d in ["household", "user-marc", "user-alice", "general"]:
            (domains_dir / d).mkdir(parents=True, exist_ok=True)

        wiki = WikiQuery(
            wiki_base=wiki_base, wiki_config=type("_FakeConfig", (), {"domains": domains_config})()
        )

        # Add pages to different domains
        wiki.add_page(
            "home-page",
            "Home",
            "Welcome home",
            {"id": "home-page", "title": "Home", "domain": "household", "kind": "page", "tags": []},
        )
        wiki.add_page(
            "marc-notes",
            "Marc Notes",
            "Personal notes",
            {
                "id": "marc-notes",
                "title": "Marc Notes",
                "domain": "user-marc",
                "kind": "page",
                "tags": [],
            },
        )
        wiki.add_page(
            "alice-secret",
            "Alice Secret",
            "Alice private data",
            {
                "id": "alice-secret",
                "title": "Alice Secret",
                "domain": "user-alice",
                "kind": "page",
                "tags": [],
            },
        )
        wiki.add_page(
            "general-faq",
            "FAQ",
            "General FAQ",
            {"id": "general-faq", "title": "FAQ", "domain": "general", "kind": "page", "tags": []},
        )
        return wiki

    def test_search_returns_all_domains_when_no_profile(self, wiki_with_config):
        """AC 5: scope_to_profile=None returns all domains."""
        domains = wiki_with_config._resolve_search_domains(domain=None, scope_to_profile=None)
        assert "household" in domains
        assert "user-marc" in domains
        assert "user-alice" in domains

    def test_explicit_domain_overrides_profile_filter(self, wiki_with_config):
        """AC 6: explicit domain param overrides scope_to_profile."""
        domains = wiki_with_config._resolve_search_domains(
            domain="household", scope_to_profile="marc"
        )
        assert domains == ["household"]

    def test_profile_filter_includes_shared_and_personal_owner(self, wiki_with_config):
        """AC 4: scoped search includes shared + matching personal domain."""
        domains = wiki_with_config._resolve_search_domains(domain=None, scope_to_profile="marc")
        assert "household" in domains
        assert "user-marc" in domains
        assert "user-alice" not in domains

    def test_unauthorized_domain_with_profile_filter_empty(self, wiki_with_config):
        """Unauthorized explicit domain blocked when profile scope is set."""
        domains = wiki_with_config._resolve_search_domains(
            domain="user-alice", scope_to_profile="marc"
        )
        assert domains == []  # Marc is not authorized for user-alice

    def test_no_config_with_profile_fails_closed(self, temp_dir):
        """When no config but scope_to_profile is set, returns empty list."""
        wiki = WikiQuery(wiki_base=temp_dir / "wiki", wiki_config=None)
        domains = wiki._resolve_search_domains(domain=None, scope_to_profile="marc")
        assert domains == []  # no config + scoped request → fail-closed

    def test_no_config_without_profile_skip_scoping(self, temp_dir):
        """When no config and no scope_to_profile, skips filtering (backward compat)."""
        wiki = WikiQuery(wiki_base=temp_dir / "wiki", wiki_config=None)
        domains = wiki._resolve_search_domains(domain=None, scope_to_profile=None)
        assert domains is None  # no config, no scope → skip filtering

    def test_no_config_respects_explicit_domain_unscoped(self, temp_dir):
        """Explicit domain is respected when no config and no profile scope."""
        wiki = WikiQuery(wiki_base=temp_dir / "wiki", wiki_config=None)
        domains = wiki._resolve_search_domains(domain="explicit", scope_to_profile=None)
        assert domains == ["explicit"]

    def test_search_without_profile_sees_all_domains(self, wiki_with_config):
        """AC 5: No profile means all domains are searched."""
        results = wiki_with_config.search(query="")
        page_titles = {r["title"] for r in results}
        assert "Home" in page_titles
        assert "Marc Notes" in page_titles
        assert "Alice Secret" in page_titles
        assert "FAQ" in page_titles

    def test_search_with_profile_sees_only_shared_and_own(self, wiki_with_config):
        """AC 4: Marc's profile excludes Alice's personal domain."""
        results = wiki_with_config.search(query="", scope_to_profile="marc")
        page_titles = {r["title"] for r in results}
        assert "Home" in page_titles  # household
        assert "Marc Notes" in page_titles  # user-marc
        assert "FAQ" in page_titles  # general (shared)
        assert "Alice Secret" not in page_titles  # user-alice excluded

    def test_explicit_domain_authorized_includes_single_domain(self, wiki_with_config):
        """Authorized explicit domain returns only that domain's pages."""
        results = wiki_with_config.search(query="", domain="user-marc", scope_to_profile="marc")
        page_titles = {r["title"] for r in results}
        assert "Marc Notes" in page_titles
        assert len(results) == 1

    def test_explicit_domain_unauthorized_rejects(self, wiki_with_config):
        """Unauthorized explicit domain with profile scope returns empty (AC: no bypass)."""
        results = wiki_with_config.search(query="", domain="user-alice", scope_to_profile="marc")
        # Should return 0 results — Marc is NOT authorized to read user-alice's domain
        assert len(results) == 0

    def test_search_other_profile_excludes_marc_personal(self, wiki_with_config):
        """AC 4: Alice's profile excludes Marc's personal domain."""
        results = wiki_with_config.search(query="", scope_to_profile="alice")
        page_titles = {r["title"] for r in results}
        assert "Home" in page_titles  # household
        assert "Alice Secret" in page_titles  # user-alice
        assert "Marc Notes" not in page_titles  # user-marc excluded
        assert "FAQ" in page_titles  # general (shared)

    def test_domain_scoping_pushed_into_index_search(self, temp_dir, domains_config):
        """Finding 3: domain filter pushed into index search so in-scope hits are not displaced.

        Marc's personal-domain pages should not be displaced by Alice's
        personal-domain pages in the unfiltered top-N ranking.
        """
        wiki_base = temp_dir / "wiki"
        wiki_base.mkdir()
        domains_dir = wiki_base / "domains"
        for d in ["household", "user-marc", "user-alice", "general"]:
            (domains_dir / d).mkdir(parents=True, exist_ok=True)

        wiki = WikiQuery(
            wiki_base=wiki_base, wiki_config=type("_FakeConfig", (), {"domains": domains_config})()
        )

        # Marc personal: 3 pages with "AI research" content
        for i in range(3):
            wiki.add_page(
                f"marc-ai-{i}",
                f"AI Notes {i}",
                "personal AI research paper NLP transformer",
                {
                    "id": f"marc-ai-{i}",
                    "title": f"AI Notes {i}",
                    "domain": "user-marc",
                    "kind": "page",
                    "tags": [],
                },
            )
        # Alice personal: 9 pages also mentioning "AI research" (many words per page)
        for i in range(9):
            wiki.add_page(
                f"alice-ai-{i}",
                f"Alice AI {i}",
                "my AI research lab notes transformer model deep learning",
                {
                    "id": f"alice-ai-{i}",
                    "title": f"Alice AI {i}",
                    "domain": "user-alice",
                    "kind": "page",
                    "tags": [],
                },
            )

        # Search with Marc's profile — should NOT see Alice's personal pages
        results = wiki.search(query="AI research transformer", scope_to_profile="marc", limit=5)
        titles = {r["title"] for r in results}
        # Marc's personal pages should appear
        assert "AI Notes 0" in titles or "AI Notes 1" in titles or "AI Notes 2" in titles
        # Alice's personal pages must NOT appear
        for i in range(9):
            assert f"Alice AI {i}" not in titles


class TestDomainsYAMLValidation:
    """Validate DomainsYAML with mixed scopes passes validation."""

    def test_mixed_scope_config_loads(self):
        """AC 1, 2, 3: Mixed scopes load correctly via DomainsYAML."""
        config = DomainsYAML.model_validate(
            {
                "domains": [
                    {
                        "id": "household",
                        "title": "Household",
                        "description": "Shared",
                        "scope": "shared",
                    },
                    {
                        "id": "user-marc",
                        "title": "Marc",
                        "description": "Personal",
                        "scope": "personal",
                        "owner": "marc",
                    },
                ]
            }
        )
        assert len(config.domains) == 2
        assert config.domains[0].scope == "shared"
        assert config.domains[1].scope == "personal"
        assert config.domains[1].owner == "marc"

    def test_backward_compat_domain_without_scope_field(self):
        """AC 3: Existing configs without scope field still load."""
        config = DomainsYAML.model_validate(
            {
                "domains": [
                    {"id": "general", "title": "General", "description": "Fallback"},
                ]
            }
        )
        assert config.domains[0].scope == "shared"
        assert config.domains[0].owner is None
