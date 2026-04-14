"""Tests for domain model and registry."""

import pytest

from llm_wiki.models.config import DomainConfig
from llm_wiki.models.domain import Domain, DomainRegistry


class TestDomain:
    """Tests for Domain class."""

    def test_create_domain(self):
        """Test creating a domain from config."""
        config = DomainConfig(
            id="test-domain",
            title="Test Domain",
            description="A test domain",
            owners=["user1", "user2"],
            promote_to_shared=True,
        )
        domain = Domain(config)

        assert domain.id == "test-domain"
        assert domain.title == "Test Domain"
        assert domain.description == "A test domain"
        assert domain.owners == ["user1", "user2"]
        assert domain.promote_to_shared is True

    def test_domain_repr(self):
        """Test domain string representation."""
        config = DomainConfig(id="test", title="Test", description="Test")
        domain = Domain(config)
        assert repr(domain) == "Domain(id='test', title='Test')"

    def test_domain_equality(self):
        """Test domain equality based on ID."""
        config1 = DomainConfig(id="test", title="Test 1", description="Test")
        config2 = DomainConfig(id="test", title="Test 2", description="Different")
        config3 = DomainConfig(id="other", title="Other", description="Test")

        domain1 = Domain(config1)
        domain2 = Domain(config2)
        domain3 = Domain(config3)

        assert domain1 == domain2  # Same ID
        assert domain1 != domain3  # Different ID

    def test_domain_hash(self):
        """Test domains can be used in sets/dicts."""
        config1 = DomainConfig(id="test", title="Test", description="Test")
        config2 = DomainConfig(id="other", title="Other", description="Test")

        domain1 = Domain(config1)
        domain2 = Domain(config2)

        domain_set = {domain1, domain2}
        assert len(domain_set) == 2
        assert domain1 in domain_set


class TestDomainRegistry:
    """Tests for DomainRegistry class."""

    def setup_method(self):
        """Reset registry before each test."""
        DomainRegistry.reset()

    def teardown_method(self):
        """Reset registry after each test."""
        DomainRegistry.reset()

    def test_initialize_registry(self):
        """Test initializing the registry."""
        configs = [
            DomainConfig(id="domain1", title="Domain 1", description="Test 1"),
            DomainConfig(id="domain2", title="Domain 2", description="Test 2"),
        ]
        registry = DomainRegistry.initialize(configs)
        assert registry.count() == 2

    def test_get_instance_before_init(self):
        """Test getting instance before initialization raises error."""
        with pytest.raises(RuntimeError, match="not initialized"):
            DomainRegistry.get_instance()

    def test_get_instance_after_init(self):
        """Test getting instance after initialization works."""
        configs = [DomainConfig(id="test", title="Test", description="Test")]
        DomainRegistry.initialize(configs)

        instance = DomainRegistry.get_instance()
        assert instance.count() == 1

    def test_singleton_pattern(self):
        """Test registry follows singleton pattern."""
        configs = [DomainConfig(id="test", title="Test", description="Test")]
        registry1 = DomainRegistry.initialize(configs)
        registry2 = DomainRegistry.get_instance()
        assert registry1 is registry2

    def test_reinitialize_clears_domains(self):
        """Test re-initializing clears previous domains."""
        configs1 = [
            DomainConfig(id="domain1", title="Domain 1", description="Test"),
            DomainConfig(id="domain2", title="Domain 2", description="Test"),
        ]
        registry = DomainRegistry.initialize(configs1)
        assert registry.count() == 2

        configs2 = [DomainConfig(id="domain3", title="Domain 3", description="Test")]
        registry.initialize(configs2)
        assert registry.count() == 1
        assert registry.exists("domain3")
        assert not registry.exists("domain1")

    def test_get_domain(self):
        """Test getting a domain by ID."""
        configs = [
            DomainConfig(id="test", title="Test", description="Test"),
        ]
        registry = DomainRegistry.initialize(configs)

        domain = registry.get("test")
        assert domain is not None
        assert domain.id == "test"

    def test_get_missing_domain(self):
        """Test getting a missing domain returns None."""
        configs = [DomainConfig(id="test", title="Test", description="Test")]
        registry = DomainRegistry.initialize(configs)

        domain = registry.get("missing")
        assert domain is None

    def test_get_or_raise(self):
        """Test get_or_raise returns domain when it exists."""
        configs = [DomainConfig(id="test", title="Test", description="Test")]
        registry = DomainRegistry.initialize(configs)

        domain = registry.get_or_raise("test")
        assert domain.id == "test"

    def test_get_or_raise_missing(self):
        """Test get_or_raise raises when domain missing."""
        configs = [DomainConfig(id="test", title="Test", description="Test")]
        registry = DomainRegistry.initialize(configs)

        with pytest.raises(KeyError, match="Domain not found: missing"):
            registry.get_or_raise("missing")

    def test_exists(self):
        """Test checking if domain exists."""
        configs = [DomainConfig(id="test", title="Test", description="Test")]
        registry = DomainRegistry.initialize(configs)

        assert registry.exists("test")
        assert not registry.exists("missing")

    def test_list_all(self):
        """Test listing all domains."""
        configs = [
            DomainConfig(id="domain1", title="Domain 1", description="Test"),
            DomainConfig(id="domain2", title="Domain 2", description="Test"),
        ]
        registry = DomainRegistry.initialize(configs)

        domains = registry.list_all()
        assert len(domains) == 2
        domain_ids = {d.id for d in domains}
        assert domain_ids == {"domain1", "domain2"}

    def test_list_ids(self):
        """Test listing domain IDs."""
        configs = [
            DomainConfig(id="domain1", title="Domain 1", description="Test"),
            DomainConfig(id="domain2", title="Domain 2", description="Test"),
        ]
        registry = DomainRegistry.initialize(configs)

        ids = registry.list_ids()
        assert set(ids) == {"domain1", "domain2"}

    def test_get_promotable_domains(self):
        """Test getting domains that allow promotion."""
        configs = [
            DomainConfig(
                id="promotable", title="Promotable", description="Test", promote_to_shared=True
            ),
            DomainConfig(
                id="not-promotable",
                title="Not Promotable",
                description="Test",
                promote_to_shared=False,
            ),
        ]
        registry = DomainRegistry.initialize(configs)

        promotable = registry.get_promotable_domains()
        assert len(promotable) == 1
        assert promotable[0].id == "promotable"


class TestDomainRegistryWithRealConfig:
    """Tests using the actual config from the repo."""

    def setup_method(self):
        """Reset registry before each test."""
        DomainRegistry.reset()

    def teardown_method(self):
        """Reset registry after each test."""
        DomainRegistry.reset()

    def test_load_real_domains(self):
        """Test loading domains from real config."""
        from llm_wiki.config.loader import load_config

        try:
            config = load_config("config")
        except Exception:
            pytest.skip("Config directory not found")

        registry = DomainRegistry.initialize(config.domains.domains)

        # Verify expected domains exist
        assert registry.exists("vulpine-solutions")
        assert registry.exists("home-assistant")
        assert registry.exists("homelab")
        assert registry.exists("personal")
        assert registry.exists("general")

        # Verify count
        assert registry.count() == 5

        # Test getting a specific domain
        vulpine = registry.get_or_raise("vulpine-solutions")
        assert vulpine.title == "Vulpine Solutions"
        assert vulpine.promote_to_shared is True

        # Test personal domain doesn't promote
        personal = registry.get_or_raise("personal")
        assert personal.promote_to_shared is False
