"""Tests for configuration loader."""

from pathlib import Path

import pytest

from llm_wiki.config.loader import ConfigLoader, ConfigLoadError, load_config


class TestConfigLoader:
    """Tests for ConfigLoader class."""

    def test_init_with_valid_directory(self, temp_dir: Path):
        """Test initializing with valid config directory."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        loader = ConfigLoader(config_dir)
        assert loader.config_dir == config_dir

    def test_init_with_missing_directory(self, temp_dir: Path):
        """Test initializing with missing directory raises error."""
        config_dir = temp_dir / "nonexistent"
        with pytest.raises(ConfigLoadError, match="does not exist"):
            ConfigLoader(config_dir)

    def test_init_with_file_not_directory(self, temp_dir: Path):
        """Test initializing with file instead of directory raises error."""
        config_file = temp_dir / "config.txt"
        config_file.touch()
        with pytest.raises(ConfigLoadError, match="not a directory"):
            ConfigLoader(config_file)

    def test_load_missing_file(self, temp_dir: Path):
        """Test loading missing config file raises error."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        loader = ConfigLoader(config_dir)

        with pytest.raises(ConfigLoadError, match="not found"):
            loader._load_yaml("missing.yaml")

    def test_load_invalid_yaml(self, temp_dir: Path):
        """Test loading invalid YAML raises error."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        invalid_file = config_dir / "invalid.yaml"
        invalid_file.write_text("invalid: yaml: content: {]")

        loader = ConfigLoader(config_dir)
        with pytest.raises(ConfigLoadError, match="Invalid YAML"):
            loader._load_yaml("invalid.yaml")

    def test_load_empty_file(self, temp_dir: Path):
        """Test loading empty YAML file raises error."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        empty_file = config_dir / "empty.yaml"
        empty_file.write_text("")

        loader = ConfigLoader(config_dir)
        with pytest.raises(ConfigLoadError, match="empty"):
            loader._load_yaml("empty.yaml")

    def test_load_domains_valid(self, temp_dir: Path):
        """Test loading valid domains.yaml."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        domains_file = config_dir / "domains.yaml"
        domains_file.write_text("""
domains:
  - id: test-domain
    title: Test Domain
    description: A test domain
    owners: [user]
    promote_to_shared: true
""")

        loader = ConfigLoader(config_dir)
        config = loader.load_domains()
        assert len(config.domains) == 1
        assert config.domains[0].id == "test-domain"

    def test_load_domains_invalid_schema(self, temp_dir: Path):
        """Test loading domains.yaml with invalid schema raises error."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        domains_file = config_dir / "domains.yaml"
        domains_file.write_text("""
domains:
  - id: InvalidID
    title: Test
    description: Test
""")

        loader = ConfigLoader(config_dir)
        with pytest.raises(ConfigLoadError, match="Invalid domains.yaml"):
            loader.load_domains()

    def test_load_daemon_valid(self, temp_dir: Path):
        """Test loading valid daemon.yaml."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        daemon_file = config_dir / "daemon.yaml"
        daemon_file.write_text("""
daemon:
  inbox_poll_seconds: 30
  max_parallel_jobs: 4
  log_level: DEBUG
""")

        loader = ConfigLoader(config_dir)
        config = loader.load_daemon()
        assert config.daemon.inbox_poll_seconds == 30
        assert config.daemon.max_parallel_jobs == 4
        assert config.daemon.log_level == "DEBUG"

    def test_load_routing_valid(self, temp_dir: Path):
        """Test loading valid routing.yaml."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        routing_file = config_dir / "routing.yaml"
        routing_file.write_text("""
routing:
  fallback_domain: general
  confidence_threshold: 0.8
  source_rules:
    - match: test
      default_domain: test-domain
""")

        loader = ConfigLoader(config_dir)
        config = loader.load_routing()
        assert config.routing.fallback_domain == "general"
        assert config.routing.confidence_threshold == 0.8
        assert len(config.routing.source_rules) == 1

    def test_load_models_valid(self, temp_dir: Path):
        """Test loading valid models.yaml."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        models_file = config_dir / "models.yaml"
        models_file.write_text("""
models:
  extraction:
    provider: openai
    model: gpt-4
    temperature: 0.1
contracts:
  require_schema_validation: true
""")

        loader = ConfigLoader(config_dir)
        config = loader.load_models()
        assert "extraction" in config.models
        assert config.models["extraction"].provider == "openai"
        assert config.contracts.require_schema_validation is True

    def test_load_all_configs(self, temp_dir: Path):
        """Test loading all config files together."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        # Create all config files
        (config_dir / "domains.yaml").write_text("""
domains:
  - id: general
    title: General
    description: General domain
""")

        (config_dir / "daemon.yaml").write_text("""
daemon:
  inbox_poll_seconds: 15
  log_level: INFO
""")

        (config_dir / "routing.yaml").write_text("""
routing:
  fallback_domain: general
""")

        (config_dir / "models.yaml").write_text("""
models:
  extraction:
    provider: local
    model: test
    temperature: 0.1
""")

        loader = ConfigLoader(config_dir)
        config = loader.load_all()

        assert len(config.domains.domains) == 1
        assert config.daemon.daemon.inbox_poll_seconds == 15
        assert config.routing.routing.fallback_domain == "general"
        assert "extraction" in config.models.models


class TestLoadConfigFunction:
    """Tests for load_config convenience function."""

    def test_load_config_success(self, temp_dir: Path):
        """Test load_config convenience function."""
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        # Create minimal valid configs
        (config_dir / "domains.yaml").write_text("domains: []")
        (config_dir / "daemon.yaml").write_text("daemon: {}")
        (config_dir / "routing.yaml").write_text("routing: {}")
        (config_dir / "models.yaml").write_text("models: {}")

        config = load_config(config_dir)
        assert config.domains is not None
        assert config.daemon is not None

    def test_load_config_failure(self, temp_dir: Path):
        """Test load_config fails with missing directory."""
        with pytest.raises(ConfigLoadError):
            load_config(temp_dir / "nonexistent")


class TestRealConfigFiles:
    """Tests using the actual config files from the repo."""

    def test_load_real_config_files(self):
        """Test loading the actual config files from the repo."""
        # This assumes tests are run from repo root
        config_dir = Path("config")
        if not config_dir.exists():
            pytest.skip("Config directory not found - test must run from repo root")

        config = load_config(config_dir)

        # Verify we got the expected domains
        domain_ids = [d.id for d in config.domains.domains]
        assert "vulpine-solutions" in domain_ids
        assert "home-assistant" in domain_ids
        assert "homelab" in domain_ids
        assert "personal" in domain_ids
        assert "general" in domain_ids

        # Verify daemon config has expected values
        assert config.daemon.daemon.inbox_poll_seconds == 15
        assert config.daemon.daemon.max_parallel_jobs == 2
        assert config.daemon.daemon.log_level == "INFO"

        # Verify routing config
        assert config.routing.routing.fallback_domain == "general"
        assert config.routing.routing.confidence_threshold == 0.75
