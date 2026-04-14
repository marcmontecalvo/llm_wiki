"""Pytest configuration and fixtures."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_markdown() -> str:
    """Sample markdown content for testing."""
    return """---
id: test-page
kind: page
title: Test Page
domain: general
status: draft
confidence: 0.8
sources: []
links: []
updated_at: 2026-04-13T00:00:00Z
---

# Test Page

## Summary
This is a test page.

## Notes
Some test notes.
"""


@pytest.fixture
def sample_frontmatter() -> dict:
    """Sample frontmatter dict for testing."""
    return {
        "id": "test-page",
        "kind": "page",
        "title": "Test Page",
        "domain": "general",
        "status": "draft",
        "confidence": 0.8,
        "sources": [],
        "links": [],
        "updated_at": "2026-04-13T00:00:00Z",
    }


@pytest.fixture
def wiki_root(temp_dir: Path) -> Path:
    """Create a temporary wiki root directory with structure."""
    wiki = temp_dir / "wiki_system"
    wiki.mkdir()

    # Create domain directories
    domains = wiki / "domains"
    domains.mkdir()
    for domain in ["vulpine-solutions", "home-assistant", "homelab", "personal", "general"]:
        (domains / domain).mkdir()

    # Create shared directories
    shared = wiki / "shared"
    shared.mkdir()
    for subdir in ["concepts", "entities", "synthesis"]:
        (shared / subdir).mkdir()

    # Create inbox directories
    inbox = wiki / "inbox"
    inbox.mkdir()
    for subdir in ["new", "processing", "failed", "done"]:
        (inbox / subdir).mkdir()

    # Create other directories
    (wiki / "exports").mkdir()
    (wiki / "logs").mkdir()
    (wiki / "state").mkdir()

    return wiki
