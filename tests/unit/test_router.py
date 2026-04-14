"""Tests for domain router."""

from pathlib import Path

import pytest

from llm_wiki.config.loader import load_config
from llm_wiki.ingest.router import DomainRouter


class TestDomainRouter:
    """Tests for DomainRouter."""

    @pytest.fixture
    def router(self) -> DomainRouter:
        """Create domain router with test config."""
        config = load_config(Path("config"))
        return DomainRouter(config)

    def test_route_explicit_domain(self, router: DomainRouter):
        """Test routing with explicit domain in metadata."""
        metadata = {
            "domain": "homelab",
            "source_path": "/some/random/path.md",
            "title": "Test",
        }

        domain = router.route(metadata)

        assert domain == "homelab"

    def test_route_explicit_invalid_domain_falls_back(self, router: DomainRouter):
        """Test invalid explicit domain falls back to rules."""
        metadata = {
            "domain": "nonexistent",
            "source_path": "/path/with/proxmox.md",
            "title": "Test",
        }

        domain = router.route(metadata)

        # Should ignore invalid domain and use routing rule (proxmox → homelab)
        assert domain == "homelab"

    def test_route_source_path_matching(self, router: DomainRouter):
        """Test routing based on source path matching."""
        # Test proxmox → homelab
        metadata = {
            "source_path": "/notes/proxmox-setup.md",
            "title": "Proxmox Setup",
        }
        assert router.route(metadata) == "homelab"

        # Test home-assistant → home-assistant
        metadata = {
            "source_path": "/docs/home-assistant-config.md",
            "title": "HA Config",
        }
        assert router.route(metadata) == "home-assistant"

        # Test .claude → general
        metadata = {
            "source_path": "/repos/.claude/notes.md",
            "title": "Notes",
        }
        assert router.route(metadata) == "general"

        # Test vulpine → vulpine-solutions
        metadata = {
            "source_path": "/work/vulpine-project.md",
            "title": "Project",
        }
        assert router.route(metadata) == "vulpine-solutions"

    def test_route_fallback_domain(self, router: DomainRouter):
        """Test routing falls back to default when no match."""
        metadata = {
            "source_path": "/random/unmatched/path.md",
            "title": "Random Content",
        }

        domain = router.route(metadata)

        # Should use fallback domain (general)
        assert domain == "general"

    def test_route_missing_source_path(self, router: DomainRouter):
        """Test routing without source_path."""
        metadata = {
            "title": "Test",
        }

        domain = router.route(metadata)

        # Should fall back to general (no path to match against)
        assert domain == "general"

    def test_validate_domain_valid(self, router: DomainRouter):
        """Test domain validation for valid domains."""
        assert router.validate_domain("homelab")
        assert router.validate_domain("home-assistant")
        assert router.validate_domain("vulpine-solutions")
        assert router.validate_domain("personal")
        assert router.validate_domain("general")

    def test_validate_domain_invalid(self, router: DomainRouter):
        """Test domain validation for invalid domains."""
        assert not router.validate_domain("nonexistent")
        assert not router.validate_domain("invalid-domain")
        assert not router.validate_domain("")

    def test_get_domain_for_source_path(self, router: DomainRouter):
        """Test getting domain from source path only."""
        # Should match proxmox rule
        assert router.get_domain_for_source_path("/notes/proxmox.md") == "homelab"

        # Should match home-assistant rule
        assert router.get_domain_for_source_path("/docs/home-assistant.md") == "home-assistant"

        # Should fall back to general
        assert router.get_domain_for_source_path("/random/file.md") == "general"

    def test_get_domain_for_source_path_no_explicit_override(self, router: DomainRouter):
        """Test get_domain_for_source_path ignores explicit domain."""
        # This method only uses path matching, not explicit domain
        # So it should return based on path, not metadata

        domain = router.get_domain_for_source_path("/notes/proxmox-setup.md")
        assert domain == "homelab"

    def test_routing_precedence(self, router: DomainRouter):
        """Test routing precedence order."""
        # Explicit domain takes precedence over path matching
        metadata = {
            "domain": "personal",  # Explicit
            "source_path": "/notes/proxmox.md",  # Would match homelab
            "title": "Test",
        }

        domain = router.route(metadata)

        # Should use explicit domain, not path rule
        assert domain == "personal"

    def test_case_sensitivity(self, router: DomainRouter):
        """Test routing is case-sensitive for path matching."""
        # Lowercase match should work
        metadata = {
            "source_path": "/notes/proxmox-setup.md",
            "title": "Test",
        }
        assert router.route(metadata) == "homelab"

        # Uppercase should not match (depends on routing rules)
        metadata = {
            "source_path": "/notes/PROXMOX-setup.md",
            "title": "Test",
        }
        # Should fall back to general (no match)
        assert router.route(metadata) == "general"

    def test_partial_path_matching(self, router: DomainRouter):
        """Test routing matches partial paths."""
        # "proxmox" can appear anywhere in path
        assert router.route({"source_path": "/a/b/proxmox/c/file.md"}) == "homelab"
        assert router.route({"source_path": "/proxmox-notes.md"}) == "homelab"
        assert router.route({"source_path": "/my-proxmox-setup.md"}) == "homelab"
