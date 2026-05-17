"""Configuration validation — runtime checks beyond Pydantic schemas."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from llm_wiki.config.loader import ConfigLoader, ConfigLoadError

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when configuration fails validation."""

    pass


@dataclass
class ValidationReport:
    """Accumulated validation results."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if there are no errors."""
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def validate_config(config_dir: Path) -> ValidationReport:
    """Run all runtime configuration checks.

    Validates:
    - Config files parse without error
    - Required directories exist (wiki base, domain dirs, inbox)
    - Domain IDs referenced in routing/daemon config exist
    - Cron expressions in job definitions are valid

    Args:
        config_dir: Path to configuration directory

    Returns:
        ValidationReport with errors and warnings

    Raises:
        ConfigLoadError: If config files cannot be loaded
    """
    report = ValidationReport()

    # 1. Load all config files (Pydantic validates schema here)
    try:
        loader = ConfigLoader(config_dir)
        config = loader.load_all()
    except ConfigLoadError:
        raise  # re-raise — the loader already populated the error message
    except Exception as exc:
        report.add_error(f"Failed to load configuration: {exc}")
        return report

    wiki_base = config_dir.parent  # config dir is typically wiki_base/config

    # 2. Check required directories
    _check_directories(wiki_base, config, report)

    # 3. Cross-check domain references
    _check_domain_refs(config, report)

    # 4. Validate cron expressions (if any job definitions use them)
    _check_cron_expressions(report)

    return report


def _check_directories(wiki_base: Path, config: object, report: ValidationReport) -> None:
    """Check that required wiki directories exist."""
    required_dirs = ["inbox"]
    if not hasattr(config, "domains"):
        return
    domain_ids: list[str] = [d.id for d in config.domains.domains]
    for did in domain_ids:
        required_dirs.append(f"domains/{did}")

    # shared subdirectories
    required_dirs.append("shared/concepts")
    required_dirs.append("shared/entities")

    for rel in required_dirs:
        path = wiki_base / rel
        if not path.exists():
            report.add_warning(f"Directory does not exist: {path}")


def _check_domain_refs(config: object, report: ValidationReport) -> None:
    """Ensure domain IDs referenced in configs actually exist."""
    if not hasattr(config, "domains"):
        return
    known = {d.id for d in config.domains.domains}

    # Check routing fallback domain
    if hasattr(config, "routing") and hasattr(config.routing, "routing"):
        fallback = config.routing.routing.fallback_domain
        if fallback and fallback not in known:
            report.add_error(
                f"Routing fallback domain '{fallback}' not in configured domains {sorted(known)}"
            )

    # Check duplicate check domains
    if hasattr(config, "daemon") and hasattr(config.daemon, "daemon"):
        dup_domains = getattr(config.daemon.daemon.duplicates, "check_domains", [])
        for dom in dup_domains:
            if dom not in known:
                report.add_error(
                    f"Duplicate check domain '{dom}' not in configured domains {sorted(known)}"
                )


def _check_cron_expressions(report: ValidationReport) -> None:
    """Validate known cron-style schedule strings."""
    # Currently all jobs use interval-based scheduling; this is a hook
    # for when add_job_cron or job definitions with cron expressions enter.
    pass
