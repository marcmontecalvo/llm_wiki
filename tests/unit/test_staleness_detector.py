"""Tests for staleness detector."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from llm_wiki.governance.staleness import StalenessDetector, StalenessReport


class TestStalenessDetector:
    """Tests for StalenessDetector."""

    @pytest.fixture
    def detector(self) -> StalenessDetector:
        """Create staleness detector."""
        return StalenessDetector()

    def test_analyze_page_fresh(self, detector: StalenessDetector, temp_dir: Path):
        """Test analyzing a fresh page that has been updated."""
        now = datetime.now(UTC)
        later = now + timedelta(days=1)
        test_file = temp_dir / "fresh.md"
        test_file.write_text(
            f"""---
id: fresh
title: Fresh Page
created: {now.isoformat()}
updated: {later.isoformat()}
---

Content without time-sensitive keywords.
"""
        )

        report = detector.analyze_page(test_file)

        assert report.page_id == "fresh"
        assert report.score < 0.5  # Should be low score
        assert report.never_updated is False

    def test_analyze_page_old(self, detector: StalenessDetector, temp_dir: Path):
        """Test analyzing an old page."""
        old_date = datetime.now(UTC) - timedelta(days=100)
        test_file = temp_dir / "old.md"
        test_file.write_text(
            f"""---
id: old
title: Old Page
created: {old_date.isoformat()}
updated: {old_date.isoformat()}
---

Content.
"""
        )

        report = detector.analyze_page(test_file)

        assert report.page_id == "old"
        assert report.score > 0.3  # Should have moderate score
        assert report.age_days is not None
        assert report.age_days > 90

    def test_analyze_page_very_old(self, detector: StalenessDetector, temp_dir: Path):
        """Test analyzing a very old page."""
        very_old_date = datetime.now(UTC) - timedelta(days=200)
        test_file = temp_dir / "very_old.md"
        test_file.write_text(
            f"""---
id: very_old
title: Very Old Page
created: {very_old_date.isoformat()}
updated: {very_old_date.isoformat()}
---

Content.
"""
        )

        report = detector.analyze_page(test_file)

        assert report.page_id == "very_old"
        assert report.score > 0.5  # Should have high score
        assert "very old" in " ".join(report.reasons).lower()

    def test_analyze_page_never_updated(self, detector: StalenessDetector, temp_dir: Path):
        """Test analyzing a page that was never updated."""
        old_date = datetime.now(UTC) - timedelta(days=50)
        test_file = temp_dir / "never_updated.md"
        test_file.write_text(
            f"""---
id: never_updated
title: Never Updated
created: {old_date.isoformat()}
updated: {old_date.isoformat()}
---

Content.
"""
        )

        report = detector.analyze_page(test_file)

        assert report.never_updated is True
        assert "never updated" in " ".join(report.reasons).lower()

    def test_analyze_page_time_sensitive_year(self, detector: StalenessDetector, temp_dir: Path):
        """Test detecting time-sensitive content (year)."""
        test_file = temp_dir / "time_sensitive.md"
        test_file.write_text(
            """---
id: time_sensitive
title: Time Sensitive
---

This guide was written in 2024 for current best practices.
"""
        )

        report = detector.analyze_page(test_file)

        assert report.has_time_sensitive_content is True
        assert "time-sensitive" in " ".join(report.reasons).lower()

    def test_analyze_page_time_sensitive_keywords(
        self, detector: StalenessDetector, temp_dir: Path
    ):
        """Test detecting time-sensitive keywords."""
        test_file = temp_dir / "current.md"
        test_file.write_text(
            """---
id: current
title: Current Guide
---

This is the latest version of our current recommendations.
"""
        )

        report = detector.analyze_page(test_file)

        assert report.has_time_sensitive_content is True

    def test_analyze_page_version_numbers(self, detector: StalenessDetector, temp_dir: Path):
        """Test detecting version numbers."""
        test_file = temp_dir / "version.md"
        test_file.write_text(
            """---
id: version
title: Version Guide
---

This guide covers Python version 3.11 and v2.0 of the API.
"""
        )

        report = detector.analyze_page(test_file)

        assert report.has_time_sensitive_content is True

    def test_analyze_page_many_urls(self, detector: StalenessDetector, temp_dir: Path):
        """Test detecting many external URLs."""
        urls = "\n".join([f"- https://example.com/page{i}" for i in range(10)])
        test_file = temp_dir / "urls.md"
        test_file.write_text(
            f"""---
id: urls
title: Many URLs
---

External references:
{urls}
"""
        )

        report = detector.analyze_page(test_file)

        assert any("external" in r.lower() for r in report.reasons)

    def test_analyze_page_combined_factors(self, detector: StalenessDetector, temp_dir: Path):
        """Test page with multiple staleness factors."""
        old_date = datetime.now(UTC) - timedelta(days=100)
        test_file = temp_dir / "combined.md"
        test_file.write_text(
            f"""---
id: combined
title: Combined Staleness
created: {old_date.isoformat()}
updated: {old_date.isoformat()}
---

This guide covers the latest Python 3.11 features in 2024.
See https://example.com for more info.
"""
        )

        report = detector.analyze_page(test_file)

        assert report.score > 0.5  # Multiple factors should increase score
        assert len(report.reasons) >= 2

    def test_analyze_page_parse_error(self, detector: StalenessDetector, temp_dir: Path):
        """Test handling parse error."""
        test_file = temp_dir / "invalid.md"
        test_file.write_text("---\ninvalid: yaml: syntax:\n---\nContent")

        report = detector.analyze_page(test_file)

        assert "failed to parse" in " ".join(report.reasons).lower()

    def test_calculate_age(self, detector: StalenessDetector):
        """Test age calculation."""
        # Test with datetime
        old_date = datetime.now(UTC) - timedelta(days=100)
        age = detector._calculate_age(old_date)
        assert age == 100

        # Test with ISO string
        age = detector._calculate_age(old_date.isoformat())
        assert age == 100

    def test_calculate_age_invalid(self, detector: StalenessDetector):
        """Test age calculation with invalid input."""
        age = detector._calculate_age("invalid")
        assert age is None

    def test_has_time_sensitive_content(self, detector: StalenessDetector):
        """Test time-sensitive content detection."""
        # Should detect years
        assert detector._has_time_sensitive_content("Written in 2024") is True

        # Should detect keywords
        assert detector._has_time_sensitive_content("The latest version") is True
        assert detector._has_time_sensitive_content("Current best practices") is True

        # Should detect version numbers
        assert detector._has_time_sensitive_content("Version 3.11") is True
        assert detector._has_time_sensitive_content("See v2.0 docs") is True

        # Should not detect in normal content
        assert detector._has_time_sensitive_content("Python programming basics") is False

    def test_analyze_all(self, detector: StalenessDetector, temp_dir: Path):
        """Test analyzing all pages."""
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        # Create pages with different staleness
        old_date = datetime.now(UTC) - timedelta(days=100)
        fresh_date = datetime.now(UTC)

        (domain_dir / "fresh.md").write_text(
            f"---\nid: fresh\ntitle: Fresh\ncreated: {fresh_date.isoformat()}\n---\nContent"
        )
        (domain_dir / "old.md").write_text(
            f"---\nid: old\ntitle: Old\ncreated: {old_date.isoformat()}\n---\nContent"
        )

        reports = detector.analyze_all(wiki_base)

        assert len(reports) == 2
        # Should be sorted by staleness score (descending)
        assert reports[0].score >= reports[1].score

    def test_analyze_all_min_score(self, detector: StalenessDetector, temp_dir: Path):
        """Test analyzing with minimum score filter."""
        wiki_base = temp_dir / "wiki"
        domain_dir = wiki_base / "domains" / "general" / "pages"
        domain_dir.mkdir(parents=True)

        old_date = datetime.now(UTC) - timedelta(days=100)
        fresh_date = datetime.now(UTC)

        (domain_dir / "fresh.md").write_text(
            f"---\nid: fresh\ntitle: Fresh\ncreated: {fresh_date.isoformat()}\n---\nContent"
        )
        (domain_dir / "old.md").write_text(
            f"---\nid: old\ntitle: Old\ncreated: {old_date.isoformat()}\n---\nContent"
        )

        # Only get stale pages
        reports = detector.analyze_all(wiki_base, min_score=0.3)

        # Should only include old page
        assert len(reports) <= 1
        if reports:
            assert reports[0].score >= 0.3

    def test_analyze_all_missing_domains(self, detector: StalenessDetector, temp_dir: Path):
        """Test analyzing with missing domains directory."""
        wiki_base = temp_dir / "empty"

        reports = detector.analyze_all(wiki_base)

        assert reports == []

    def test_staleness_report_dataclass(self):
        """Test StalenessReport dataclass."""
        report = StalenessReport(
            page_id="test",
            score=0.7,
            reasons=["Old", "Never updated"],
            age_days=100,
            never_updated=True,
            has_time_sensitive_content=False,
        )

        assert report.page_id == "test"
        assert report.score == 0.7
        assert len(report.reasons) == 2
        assert report.age_days == 100
        assert report.never_updated is True
        assert report.has_time_sensitive_content is False
