"""Metadata linter for wiki pages."""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from llm_wiki.index.metadata import MetadataIndex
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class LintSeverity(Enum):
    """Lint issue severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class LintIssue:
    """Represents a lint issue found in a page."""

    page_id: str
    severity: LintSeverity
    rule: str
    message: str
    field: str | None = None


class MetadataLinter:
    """Linter for validating page metadata."""

    # Required fields in frontmatter
    REQUIRED_FIELDS = {"id", "title", "domain"}

    # Valid page kinds
    VALID_KINDS = {"page", "entity", "concept", "source"}

    # Maximum tag count
    MAX_TAGS = 10

    def __init__(self, metadata_index: MetadataIndex | None = None):
        """Initialize metadata linter.

        Args:
            metadata_index: Optional metadata index for orphan detection
        """
        self.metadata_index = metadata_index

    def lint_file(self, filepath: Path) -> list[LintIssue]:
        """Lint a single markdown file.

        Args:
            filepath: Path to markdown file

        Returns:
            List of lint issues
        """
        issues: list[LintIssue] = []

        try:
            content = filepath.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)
        except Exception as e:
            issues.append(
                LintIssue(
                    page_id=filepath.stem,
                    severity=LintSeverity.ERROR,
                    rule="parse_error",
                    message=f"Failed to parse file: {e}",
                )
            )
            return issues

        page_id = metadata.get("id", filepath.stem)

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in metadata or not metadata[field]:
                issues.append(
                    LintIssue(
                        page_id=page_id,
                        severity=LintSeverity.ERROR,
                        rule="missing_required_field",
                        message=f"Missing required field: {field}",
                        field=field,
                    )
                )

        # Validate field types
        issues.extend(self._validate_field_types(page_id, metadata))

        # Validate kind
        if "kind" in metadata:
            kind = metadata["kind"]
            if kind not in self.VALID_KINDS:
                issues.append(
                    LintIssue(
                        page_id=page_id,
                        severity=LintSeverity.ERROR,
                        rule="invalid_kind",
                        message=f"Invalid kind '{kind}'. Must be one of: {self.VALID_KINDS}",
                        field="kind",
                    )
                )

        # Validate tags
        if "tags" in metadata:
            tags = metadata["tags"]
            if not isinstance(tags, list):
                issues.append(
                    LintIssue(
                        page_id=page_id,
                        severity=LintSeverity.ERROR,
                        rule="invalid_tags_type",
                        message="Tags must be a list",
                        field="tags",
                    )
                )
            elif len(tags) > self.MAX_TAGS:
                issues.append(
                    LintIssue(
                        page_id=page_id,
                        severity=LintSeverity.WARNING,
                        rule="too_many_tags",
                        message=f"Too many tags ({len(tags)}). Maximum is {self.MAX_TAGS}",
                        field="tags",
                    )
                )

        # Check for summary (recommended but not required)
        if "summary" not in metadata or not metadata["summary"]:
            issues.append(
                LintIssue(
                    page_id=page_id,
                    severity=LintSeverity.INFO,
                    rule="missing_summary",
                    message="Page has no summary",
                    field="summary",
                )
            )

        # Check for citations if this is an entity or concept
        kind = metadata.get("kind", "page")
        if kind in {"entity", "concept"} and "source" not in metadata:
            issues.append(
                LintIssue(
                    page_id=page_id,
                    severity=LintSeverity.WARNING,
                    rule="missing_source",
                    message=f"{kind.capitalize()} page should have a source citation",
                    field="source",
                )
            )

        return issues

    def _validate_field_types(self, page_id: str, metadata: dict[str, Any]) -> list[LintIssue]:
        """Validate field types in metadata.

        Args:
            page_id: Page identifier
            metadata: Page metadata

        Returns:
            List of lint issues
        """
        issues: list[LintIssue] = []

        # String fields
        for field in ["id", "title", "domain", "kind", "summary", "source"]:
            if field in metadata and not isinstance(metadata[field], str):
                issues.append(
                    LintIssue(
                        page_id=page_id,
                        severity=LintSeverity.ERROR,
                        rule="invalid_field_type",
                        message=f"Field '{field}' must be a string",
                        field=field,
                    )
                )

        # List fields
        for field in ["tags", "entities", "concepts"]:
            if field in metadata and not isinstance(metadata[field], list):
                issues.append(
                    LintIssue(
                        page_id=page_id,
                        severity=LintSeverity.ERROR,
                        rule="invalid_field_type",
                        message=f"Field '{field}' must be a list",
                        field=field,
                    )
                )

        return issues

    def detect_orphans(self) -> list[str]:
        """Detect orphan pages (no incoming links).

        Requires metadata_index to be set.

        Returns:
            List of page IDs with no incoming links

        Raises:
            ValueError: If metadata_index not set
        """
        if not self.metadata_index:
            raise ValueError("metadata_index required for orphan detection")

        orphans = []

        for page_id in self.metadata_index.pages:
            # Check if any other page links to this one
            has_incoming = False

            for other_id, other_meta in self.metadata_index.pages.items():
                if other_id == page_id:
                    continue

                # Check in related_pages field if it exists
                related = other_meta.get("related_pages", [])
                if page_id in related:
                    has_incoming = True
                    break

            if not has_incoming:
                orphans.append(page_id)

        return orphans

    def lint_domain(self, domain_path: Path) -> list[LintIssue]:
        """Lint all pages in a domain.

        Args:
            domain_path: Path to domain directory

        Returns:
            List of all lint issues
        """
        issues: list[LintIssue] = []

        pages_dir = domain_path / "pages"
        if not pages_dir.exists():
            logger.warning(f"Pages directory not found: {pages_dir}")
            return issues

        for page_file in pages_dir.glob("*.md"):
            issues.extend(self.lint_file(page_file))

        return issues

    def lint_all(self, wiki_base: Path | None = None) -> list[LintIssue]:
        """Lint all pages in the wiki.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)

        Returns:
            List of all lint issues
        """
        wiki_base = wiki_base or Path("wiki_system")
        issues: list[LintIssue] = []

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return issues

        for domain_dir in domains_dir.iterdir():
            if domain_dir.is_dir():
                issues.extend(self.lint_domain(domain_dir))

        return issues
