"""Tests for configuration validator."""

from pathlib import Path

import pytest

from llm_wiki.config.loader import ConfigLoadError
from llm_wiki.config.validator import (
    ValidationReport,
    validate_config,
)


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_default_is_valid(self):
        report = ValidationReport()
        assert report.is_valid is True

    def test_errors_make_invalid(self):
        report = ValidationReport()
        report.add_error("bad config")
        assert report.is_valid is False

    def test_warnings_do_not_affect_validity(self):
        report = ValidationReport()
        report.add_warning("missing dir")
        assert report.is_valid is True

    def test_multiple_errors(self):
        report = ValidationReport()
        report.add_error("e1")
        report.add_error("e2")
        assert len(report.errors) == 2
        assert report.is_valid is False

    def test_warnings_listed(self):
        report = ValidationReport()
        report.add_warning("w1")
        report.add_warning("w2")
        assert len(report.warnings) == 2


class TestValidateConfig:
    """Tests for validate_config entry point."""

    def _write_minimal(self, config_dir: Path) -> None:
        """Write minimal valid config files."""
        (config_dir / "domains.yaml").write_text("""
domains:
  - id: general
    title: General
    description: General domain
""")
        (config_dir / "daemon.yaml").write_text("daemon: {}\n")
        (config_dir / "routing.yaml").write_text("""
routing:
  fallback_domain: general
""")
        (config_dir / "models.yaml").write_text("models: {}\n")

    def test_missing_config_dir_raises(self, temp_dir: Path):
        with pytest.raises(ConfigLoadError):
            validate_config(temp_dir / "nonexistent")

    def test_invalid_domains_yaml_raises(self, temp_dir: Path):
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        (config_dir / "domains.yaml").write_text(
            "domains:\n  - id: INVALID_ID\n    title: T\n    description: D\n"
        )
        (config_dir / "daemon.yaml").write_text("daemon: {}\n")
        (config_dir / "routing.yaml").write_text("routing: {}\n")
        (config_dir / "models.yaml").write_text("models: {}\n")

        with pytest.raises(ConfigLoadError):
            validate_config(config_dir)

    def test_wrong_fallback_domain(self, temp_dir: Path):
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        (config_dir / "domains.yaml").write_text("""
domains:
  - id: general
    title: General
    description: General domain
""")
        (config_dir / "daemon.yaml").write_text("daemon: {}\n")
        (config_dir / "routing.yaml").write_text("""
routing:
  fallback_domain: missing-domain
""")
        (config_dir / "models.yaml").write_text("models: {}\n")

        report = validate_config(config_dir)
        assert not report.is_valid
        assert any("missing-domain" in e for e in report.errors)

    def test_wrong_duplicate_check_domain(self, temp_dir: Path):
        config_dir = temp_dir / "config"
        config_dir.mkdir()

        (config_dir / "domains.yaml").write_text("""
domains:
  - id: general
    title: General
    description: General domain
""")
        (config_dir / "daemon.yaml").write_text("""
daemon:
  duplicates:
    check_domains:
      - missing
""")
        (config_dir / "routing.yaml").write_text("routing: {}\n")
        (config_dir / "models.yaml").write_text("models: {}\n")

        report = validate_config(config_dir)
        assert not report.is_valid
        assert any("missing" in e for e in report.errors)

    def test_valid_config_no_errors(self, temp_dir: Path):
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        self._write_minimal(config_dir)

        report = validate_config(config_dir)
        assert report.is_valid

    def test_missing_directory_warnings(self, temp_dir: Path):
        config_dir = temp_dir / "config"
        config_dir.mkdir()
        self._write_minimal(config_dir)

        report = validate_config(config_dir)
        # Should warn about missing dirs but not error
        assert report.is_valid
        assert any("inbox" in w for w in report.warnings)

    def test_no_config_dir_exception_type(self, temp_dir: Path):
        """Ensure ConfigLoadError (not generic Exception) propagates."""
        with pytest.raises(ConfigLoadError, match="does not exist"):
            validate_config(temp_dir / "nonexistent")
