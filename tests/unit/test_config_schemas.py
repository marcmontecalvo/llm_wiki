"""Tests for configuration schemas."""

import pytest
from pydantic import ValidationError

from llm_wiki.models.config import (
    DaemonConfig,
    DomainConfig,
    DomainsYAML,
    ModelProviderConfig,
    ModelsYAML,
    RoutingConfig,
    SourceRule,
)


class TestDomainConfig:
    """Tests for DomainConfig schema."""

    def test_valid_domain(self):
        """Test valid domain configuration."""
        domain = DomainConfig(
            id="test-domain",
            title="Test Domain",
            description="A test domain",
            owners=["user"],
            promote_to_shared=True,
        )
        assert domain.id == "test-domain"
        assert domain.title == "Test Domain"
        assert domain.promote_to_shared is True

    def test_domain_id_lowercase_validation(self):
        """Test domain ID must be lowercase."""
        with pytest.raises(ValidationError, match="must be lowercase"):
            DomainConfig(
                id="TestDomain",
                title="Test",
                description="Test",
            )

    def test_domain_id_invalid_chars(self):
        """Test domain ID validation rejects invalid characters."""
        with pytest.raises(ValidationError, match="must be alphanumeric"):
            DomainConfig(
                id="test@domain",
                title="Test",
                description="Test",
            )

    def test_domain_id_empty(self):
        """Test domain ID cannot be empty."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            DomainConfig(
                id="",
                title="Test",
                description="Test",
            )


class TestDomainsYAML:
    """Tests for DomainsYAML schema."""

    def test_valid_domains_list(self):
        """Test valid domains list."""
        config = DomainsYAML(
            domains=[
                DomainConfig(id="domain1", title="Domain 1", description="Test 1"),
                DomainConfig(id="domain2", title="Domain 2", description="Test 2"),
            ]
        )
        assert len(config.domains) == 2
        assert config.domains[0].id == "domain1"

    def test_duplicate_domain_ids(self):
        """Test duplicate domain IDs are rejected."""
        with pytest.raises(ValidationError, match="must be unique"):
            DomainsYAML(
                domains=[
                    DomainConfig(id="same", title="Domain 1", description="Test 1"),
                    DomainConfig(id="same", title="Domain 2", description="Test 2"),
                ]
            )


class TestDaemonConfig:
    """Tests for DaemonConfig schema."""

    def test_default_values(self):
        """Test daemon config with defaults."""
        config = DaemonConfig()
        assert config.inbox_poll_seconds == 15
        assert config.max_parallel_jobs == 2
        assert config.log_level == "INFO"
        assert config.review_queue_enabled is True

    def test_custom_values(self):
        """Test daemon config with custom values."""
        config = DaemonConfig(
            inbox_poll_seconds=30,
            max_parallel_jobs=4,
            log_level="DEBUG",
        )
        assert config.inbox_poll_seconds == 30
        assert config.max_parallel_jobs == 4
        assert config.log_level == "DEBUG"

    def test_validation_min_values(self):
        """Test validation enforces minimum values."""
        with pytest.raises(ValidationError):
            DaemonConfig(inbox_poll_seconds=0)

        with pytest.raises(ValidationError):
            DaemonConfig(max_parallel_jobs=0)

    def test_validation_max_parallel_jobs(self):
        """Test max_parallel_jobs upper bound."""
        with pytest.raises(ValidationError):
            DaemonConfig(max_parallel_jobs=100)

    def test_log_level_validation(self):
        """Test log level must be valid."""
        with pytest.raises(ValidationError):
            DaemonConfig(log_level="INVALID")


class TestRoutingConfig:
    """Tests for RoutingConfig schema."""

    def test_default_values(self):
        """Test routing config defaults."""
        config = RoutingConfig()
        assert config.fallback_domain == "general"
        assert config.confidence_threshold == 0.75
        assert config.explicit_override_frontmatter_key == "domain"

    def test_source_rules(self):
        """Test source rules configuration."""
        config = RoutingConfig(
            source_rules=[
                SourceRule(match="test", default_domain="test-domain"),
                SourceRule(match="prod", default_domain="prod-domain"),
            ]
        )
        assert len(config.source_rules) == 2
        assert config.source_rules[0].match == "test"

    def test_confidence_threshold_bounds(self):
        """Test confidence threshold validation."""
        with pytest.raises(ValidationError):
            RoutingConfig(confidence_threshold=1.5)

        with pytest.raises(ValidationError):
            RoutingConfig(confidence_threshold=-0.1)


class TestModelProviderConfig:
    """Tests for ModelProviderConfig schema."""

    def test_valid_config(self):
        """Test valid model provider config."""
        config = ModelProviderConfig(
            provider="openai",
            model="gpt-4",
            temperature=0.2,
        )
        assert config.provider == "openai"
        assert config.model == "gpt-4"
        assert config.temperature == 0.2

    def test_temperature_bounds(self):
        """Test temperature validation."""
        with pytest.raises(ValidationError):
            ModelProviderConfig(provider="test", model="test", temperature=3.0)

        with pytest.raises(ValidationError):
            ModelProviderConfig(provider="test", model="test", temperature=-0.1)


class TestModelsYAML:
    """Tests for ModelsYAML schema."""

    def test_valid_config(self):
        """Test valid models configuration."""
        config = ModelsYAML(
            models={
                "extraction": ModelProviderConfig(
                    provider="openai", model="gpt-4", temperature=0.1
                ),
                "integration": ModelProviderConfig(
                    provider="openai", model="gpt-4", temperature=0.1
                ),
            }
        )
        assert "extraction" in config.models
        assert config.models["extraction"].model == "gpt-4"

    def test_contracts_defaults(self):
        """Test contracts use defaults."""
        config = ModelsYAML(
            models={
                "extraction": ModelProviderConfig(provider="local", model="test", temperature=0.1)
            }
        )
        assert config.contracts.require_schema_validation is True
        assert config.contracts.allow_freeform_page_writes is False
