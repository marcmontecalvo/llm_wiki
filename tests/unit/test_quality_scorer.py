"""Tests for quality scorer."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from llm_wiki.governance.quality import QualityReport, QualityScorer


class TestQualityScorer:
    """Tests for QualityScorer."""

    @pytest.fixture
    def scorer(self) -> QualityScorer:
        """Create quality scorer."""
        return QualityScorer()

    def test_score_page_high_quality(self, scorer: QualityScorer, temp_dir: Path):
        """Test scoring a high-quality page."""
        now = datetime.now(UTC)
        later = now + timedelta(days=1)
        test_file = temp_dir / "high_quality.md"
        test_file.write_text(
            f"""---
id: high
title: High Quality Page
summary: A well-documented page
tags:
  - test
  - quality
kind: page
source: https://example.com
created: {now.isoformat()}
updated: {later.isoformat()}
---

# Introduction

This is a comprehensive page with multiple sections.

## Features

- Well structured
- Has headings
- Has bullet points
- Good length content

## Details

More detailed information here to meet the minimum content length requirements.
"""
        )

        report = scorer.score_page(test_file)

        assert report.page_id == "high"
        assert report.score > 0.7  # High quality
        assert len(report.issues) == 0 or all("no" not in i.lower() for i in report.issues)

    def test_score_page_low_quality(self, scorer: QualityScorer, temp_dir: Path):
        """Test scoring a low-quality page."""
        test_file = temp_dir / "low_quality.md"
        test_file.write_text(
            """---
id: low
title: Low Quality
---

Short content.
"""
        )

        report = scorer.score_page(test_file)

        assert report.page_id == "low"
        assert report.score < 0.5  # Low quality
        assert len(report.issues) > 0

    def test_score_page_parse_error(self, scorer: QualityScorer, temp_dir: Path):
        """Test handling parse error."""
        test_file = temp_dir / "invalid.md"
        test_file.write_text("---\ninvalid: yaml: syntax:\n---\nContent")

        report = scorer.score_page(test_file)

        assert report.score == 0.0
        assert any("failed to parse" in i.lower() for i in report.issues)

    def test_score_metadata_complete(self, scorer: QualityScorer):
        """Test metadata scoring with complete metadata."""
        metadata: dict[str, Any] = {
            "summary": "Test summary",
            "tags": ["tag1", "tag2"],
            "kind": "page",
            "source": "https://example.com",
        }
        issues: list[str] = []

        score = scorer._score_metadata(metadata, issues)

        assert score > 0.8
        assert len(issues) == 0

    def test_score_metadata_incomplete(self, scorer: QualityScorer):
        """Test metadata scoring with incomplete metadata."""
        metadata: dict[str, Any] = {"title": "Test"}
        issues: list[str] = []

        score = scorer._score_metadata(metadata, issues)

        assert score < 0.7
        assert len(issues) > 0

    def test_score_content_good(self, scorer: QualityScorer):
        """Test content scoring with good content."""
        content = (
            """
# Heading

This is a well-structured page with good length.

- Bullet point 1
- Bullet point 2

## Another Heading

More content to reach the minimum length threshold.
"""
            * 3
        )
        issues: list[str] = []

        score = scorer._score_content(content, issues)

        assert score > 0.7
        assert len(issues) == 0

    def test_score_content_short(self, scorer: QualityScorer):
        """Test content scoring with short content."""
        content = "Short"
        issues: list[str] = []

        score = scorer._score_content(content, issues)

        assert score < 0.5
        assert any("short" in i.lower() for i in issues)

    def test_score_content_no_structure(self, scorer: QualityScorer):
        """Test content scoring with no structure."""
        content = "Plain text without any headings or lists." * 20
        issues: list[str] = []

        scorer._score_content(content, issues)

        assert any("heading" in i.lower() for i in issues)
        assert any("list" in i.lower() for i in issues)

    def test_score_recency_updated(self, scorer: QualityScorer):
        """Test recency scoring for updated page."""
        now = datetime.now(UTC)
        later = now + timedelta(days=1)
        metadata: dict[str, Any] = {
            "created": now.isoformat(),
            "updated": later.isoformat(),
        }
        issues: list[str] = []

        score = scorer._score_recency(metadata, issues)

        assert score == 1.0
        assert len(issues) == 0

    def test_score_recency_never_updated(self, scorer: QualityScorer):
        """Test recency scoring for never-updated page."""
        now = datetime.now(UTC)
        metadata: dict[str, Any] = {
            "created": now.isoformat(),
            "updated": now.isoformat(),
        }
        issues: list[str] = []

        score = scorer._score_recency(metadata, issues)

        assert score == 0.3
        assert any("never updated" in i.lower() for i in issues)

    def test_score_recency_no_timestamp(self, scorer: QualityScorer):
        """Test recency scoring without timestamp."""
        metadata: dict[str, Any] = {}
        issues: list[str] = []

        score = scorer._score_recency(metadata, issues)

        assert score == 0.0
        assert any("timestamp" in i.lower() for i in issues)

    def test_score_all(self, scorer: QualityScorer, temp_dir: Path):
        """Test scoring all pages."""
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        # Create pages with different quality
        (pages_dir / "good.md").write_text(
            """---
id: good
title: Good Page
summary: Test
tags: [test]
source: http://example.com
---

# Content

Good content with structure."""
        )

        (pages_dir / "bad.md").write_text("---\nid: bad\ntitle: Bad\n---\nShort")

        reports = scorer.score_all(wiki_base)

        assert len(reports) == 2
        # Should be sorted by quality (ascending - lowest first)
        assert reports[0].score <= reports[1].score

    def test_score_all_max_score_filter(self, scorer: QualityScorer, temp_dir: Path):
        """Test scoring with max score filter."""
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        (pages_dir / "good.md").write_text(
            """---
id: good
title: Good
summary: Test
tags: [test]
source: http://example.com
---

# Content

Good content."""
        )

        (pages_dir / "bad.md").write_text("---\nid: bad\ntitle: Bad\n---\nShort")

        # Only get low-quality pages
        reports = scorer.score_all(wiki_base, max_score=0.5)

        assert all(r.score <= 0.5 for r in reports)

    def test_quality_report_dataclass(self):
        """Test QualityReport dataclass."""
        report = QualityReport(
            page_id="test",
            score=0.75,
            factors={"metadata": 0.8, "content": 0.7},
            issues=["Minor issue"],
        )

        assert report.page_id == "test"
        assert report.score == 0.75
        assert report.factors["metadata"] == 0.8
        assert len(report.issues) == 1
