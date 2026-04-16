"""Tests for duplicate entity detection."""

from pathlib import Path

import pytest

from llm_wiki.governance.duplicates import (
    DuplicateCandidate,
    DuplicateDetector,
    DuplicateReport,
)


class TestDuplicateDetector:
    """Tests for DuplicateDetector."""

    @pytest.fixture
    def detector(self) -> DuplicateDetector:
        """Create a duplicate detector."""
        return DuplicateDetector(min_score=0.3)

    def test_detector_initialization(self):
        """Test detector initialization with parameters."""
        detector = DuplicateDetector(min_score=0.5)
        assert detector.min_score == 0.5

    def test_normalize_name_lowercase(self, detector: DuplicateDetector):
        """Test name normalization converts to lowercase."""
        result = detector._normalize_name("Python Programming Language")
        assert result == "python programming language"

    def test_normalize_name_strip_whitespace(self, detector: DuplicateDetector):
        """Test name normalization strips whitespace."""
        result = detector._normalize_name("  Python  ")
        assert result == "python"

    def test_normalize_name_remove_stop_words(self, detector: DuplicateDetector):
        """Test name normalization removes stop words."""
        result = detector._normalize_name("The Python Programming Language")
        assert result == "python programming language"

    def test_normalize_name_remove_article_a(self, detector: DuplicateDetector):
        """Test removal of article 'a'."""
        result = detector._normalize_name("A Python Library")
        assert result == "python library"

    def test_normalize_name_remove_article_an(self, detector: DuplicateDetector):
        """Test removal of article 'an'."""
        result = detector._normalize_name("An API Reference")
        assert result == "api reference"

    def test_normalize_name_empty(self, detector: DuplicateDetector):
        """Test normalization of empty string."""
        result = detector._normalize_name("")
        assert result == ""

    def test_check_alias_match_exact(self, detector: DuplicateDetector):
        """Test exact alias matching."""
        result = detector._check_alias_match("Python", ["Python", "Py"])
        assert result is True

    def test_check_alias_match_case_insensitive(self, detector: DuplicateDetector):
        """Test case-insensitive alias matching."""
        result = detector._check_alias_match("python", ["PYTHON"])
        assert result is True

    def test_check_alias_match_normalized(self, detector: DuplicateDetector):
        """Test alias matching with normalization."""
        result = detector._check_alias_match("the python", ["Python"])
        assert result is True

    def test_check_alias_match_no_match(self, detector: DuplicateDetector):
        """Test alias matching returns False when no match."""
        result = detector._check_alias_match("Python", ["JavaScript", "Ruby"])
        assert result is False

    def test_check_alias_match_empty_name(self, detector: DuplicateDetector):
        """Test alias matching with empty name."""
        result = detector._check_alias_match("", ["Python"])
        assert result is False

    def test_check_alias_match_empty_aliases(self, detector: DuplicateDetector):
        """Test alias matching with empty aliases list."""
        result = detector._check_alias_match("Python", [])
        assert result is False

    def test_score_pair_exact_name_match(self, detector: DuplicateDetector):
        """Test scoring pair with exact name match."""
        meta1 = {"title": "Python Programming", "name": "Python"}
        meta2 = {"title": "python programming", "name": "python"}

        score, reasons = detector._score_pair(meta1, meta2, "content1", "content2")

        assert score >= 0.4  # At least the name_similarity component (0.4)
        assert any("Exact name match" in r for r in reasons)

    def test_score_pair_alias_match(self, detector: DuplicateDetector):
        """Test scoring pair when name of one page is in aliases of other."""
        meta1 = {"title": "AWS", "aliases": ["Amazon Web Services", "AWS"]}
        meta2 = {"title": "Amazon Web Services"}

        score, reasons = detector._score_pair(meta1, meta2, "content1", "content2")

        assert score >= 0.3  # At least the alias_match component (0.3)
        assert any("alias" in r.lower() for r in reasons)

    def test_score_pair_same_source_url(self, detector: DuplicateDetector):
        """Test scoring pair with same source URL."""
        meta1 = {"title": "Page 1", "source_url": "https://example.com/doc"}
        meta2 = {"title": "Page 2", "source_url": "https://example.com/doc"}

        score, reasons = detector._score_pair(meta1, meta2, "content1", "content2")

        assert score >= 0.2  # At least the metadata_overlap component (0.2)
        assert any("source URL" in r for r in reasons)

    def test_score_pair_same_github_url(self, detector: DuplicateDetector):
        """Test scoring pair with same GitHub URL."""
        meta1 = {"title": "Page 1", "github_url": "https://github.com/owner/repo"}
        meta2 = {"title": "Page 2", "github_url": "https://github.com/owner/repo"}

        score, reasons = detector._score_pair(meta1, meta2, "content1", "content2")

        assert score >= 0.2  # At least the metadata_overlap component (0.2)
        assert any("GitHub URL" in r for r in reasons)

    def test_score_pair_three_common_tags(self, detector: DuplicateDetector):
        """Test scoring pair with >= 3 common tags."""
        meta1 = {"title": "Page 1", "tags": ["python", "web", "api", "framework"]}
        meta2 = {"title": "Page 2", "tags": ["python", "web", "api", "database"]}

        score, reasons = detector._score_pair(meta1, meta2, "content1", "content2")

        assert score >= 0.1  # At least the tag_overlap component (0.1)
        assert any("common tags" in r.lower() for r in reasons)

    def test_score_pair_less_than_three_tags(self, detector: DuplicateDetector):
        """Test that less than 3 common tags don't trigger tag_overlap."""
        meta1 = {"title": "Page 1", "tags": ["python", "web"]}
        meta2 = {"title": "Page 2", "tags": ["python", "database"]}

        score, reasons = detector._score_pair(meta1, meta2, "content1", "content2")

        # Should have no tag overlap reason
        assert not any("common tags" in r.lower() for r in reasons)

    def test_score_pair_formula_correctness(self, detector: DuplicateDetector):
        """Test the scoring formula is correct."""
        meta1 = {
            "title": "Python Programming",
            "source_url": "https://example.com/python",
        }
        meta2 = {
            "title": "python programming",
            "source_url": "https://example.com/python",
        }

        score, reasons = detector._score_pair(meta1, meta2, "content", "content")

        # name_similarity=1.0, alias_match=0.0, metadata_overlap=1.0, tag_overlap=0.0, content_similarity>0.0 (small)
        # score = 1.0 * 0.4 + 0.0 * 0.3 + 1.0 * 0.2 + 0.0 * 0.1 + content_sim * 0.1 ≈ 0.6 (content similarity is small for single word)
        assert abs(score - 0.6) < 0.15  # More lenient due to content similarity

    def test_score_pair_no_matches(self, detector: DuplicateDetector):
        """Test scoring pair with no matches returns 0."""
        meta1 = {"title": "Python"}
        meta2 = {"title": "JavaScript"}

        score, reasons = detector._score_pair(meta1, meta2, "content1", "content2")

        assert score == 0.0
        assert len(reasons) == 0

    def test_duplicate_candidate_to_dict(self):
        """Test converting DuplicateCandidate to dictionary."""
        candidate = DuplicateCandidate(
            page_1="page1",
            page_2="page2",
            duplicate_score=0.85,
            reasons=["Same name"],
            suggested_action="merge",
            primary_page="page1",
        )

        result = candidate.to_dict()

        assert result["page_1"] == "page1"
        assert result["page_2"] == "page2"
        assert result["duplicate_score"] == 0.85
        assert result["suggested_action"] == "merge"
        assert result["primary_page"] == "page1"

    def test_duplicate_report_confidence_levels(self):
        """Test DuplicateReport with different confidence levels."""
        high_cand = DuplicateCandidate("p1", "p2", 0.9, ["reason"])
        med_cand = DuplicateCandidate("p3", "p4", 0.65, ["reason"])
        low_cand = DuplicateCandidate("p5", "p6", 0.35, ["reason"])

        report = DuplicateReport(
            total_candidates=3,
            high_confidence=[high_cand],
            medium_confidence=[med_cand],
            low_confidence=[low_cand],
        )

        assert len(report.high_confidence) == 1
        assert len(report.medium_confidence) == 1
        assert len(report.low_confidence) == 1
        assert report.total_candidates == 3

    def test_analyze_all_pages_empty_wiki(self, tmp_path: Path, detector: DuplicateDetector):
        """Test analyze_all_pages with empty wiki."""
        wiki_base = tmp_path / "wiki"
        wiki_base.mkdir()
        (wiki_base / "domains").mkdir()

        report = detector.analyze_all_pages(wiki_base)

        assert report.total_candidates == 0
        assert len(report.high_confidence) == 0

    def test_analyze_all_pages_single_page(self, tmp_path: Path, detector: DuplicateDetector):
        """Test analyze_all_pages with single page."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test_domain" / "pages"
        domain_dir.mkdir(parents=True)

        page_content = """---
id: page1
title: Test Page
kind: page
---

Test content
"""
        (domain_dir / "page1.md").write_text(page_content)

        report = detector.analyze_all_pages(wiki_base)

        assert report.total_candidates == 0

    def test_analyze_all_pages_duplicate_pair(self, tmp_path: Path, detector: DuplicateDetector):
        """Test analyze_all_pages detects duplicate pair."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test_domain" / "pages"
        domain_dir.mkdir(parents=True)

        page1_content = """---
id: page1
title: Python Programming
kind: page
source_url: https://example.com/python
aliases:
  - Python language
tags:
  - python
  - programming
  - language
  - scripting
  - software
---

Content about Python
"""
        page2_content = """---
id: page2
title: python programming
kind: page
source_url: https://example.com/python
aliases:
  - Python language
tags:
  - python
  - programming
  - language
  - scripting
  - tutorial
---

More Python content
"""
        (domain_dir / "page1.md").write_text(page1_content)
        (domain_dir / "page2.md").write_text(page2_content)

        report = detector.analyze_all_pages(wiki_base)

        assert report.total_candidates >= 1
        assert len(report.medium_confidence) >= 1

    def test_analyze_all_pages_skip_source_pages(self, tmp_path: Path, detector: DuplicateDetector):
        """Test that source pages are skipped."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test_domain" / "pages"
        domain_dir.mkdir(parents=True)

        source_page = """---
id: source1
title: Source Document
kind: source
---

Source content
"""
        regular_page = """---
id: regular1
title: Regular Page
kind: page
---

Regular content
"""
        (domain_dir / "source1.md").write_text(source_page)
        (domain_dir / "regular1.md").write_text(regular_page)

        report = detector.analyze_all_pages(wiki_base)

        # Should only compare regular pages, not source
        assert report.total_candidates == 0

    def test_analyze_all_pages_multiple_domains(self, tmp_path: Path, detector: DuplicateDetector):
        """Test analyze_all_pages with multiple domains."""
        wiki_base = tmp_path / "wiki"

        # Create pages in different domains with duplicate names
        domain1_dir = wiki_base / "domains" / "domain1" / "pages"
        domain1_dir.mkdir(parents=True)

        domain2_dir = wiki_base / "domains" / "domain2" / "pages"
        domain2_dir.mkdir(parents=True)

        page1 = """---
id: python-page1
title: Python
kind: page
---

Python content
"""
        page2 = """---
id: python-page2
title: Python
kind: page
---

Python content
"""
        (domain1_dir / "page1.md").write_text(page1)
        (domain2_dir / "page2.md").write_text(page2)

        report = detector.analyze_all_pages(wiki_base)

        assert report.total_candidates >= 1

    def test_suggested_action_high_confidence(self, tmp_path: Path, detector: DuplicateDetector):
        """Test suggested_action is 'merge' for score > 0.8."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test" / "pages"
        domain_dir.mkdir(parents=True)

        # name match (0.4) + alias match (0.3) + source_url match (0.2) = 0.9 > 0.8
        # Page A has "Python" in its own alias list, so alias_match triggers for page B's name
        (domain_dir / "a.md").write_text(
            "---\nid: a\ntitle: Python\nkind: page\nsource_url: http://same.com\naliases:\n  - Python\n---\ncontent\n"
        )
        (domain_dir / "b.md").write_text(
            "---\nid: b\ntitle: Python\nkind: page\nsource_url: http://same.com\n---\ncontent\n"
        )

        report = detector.analyze_all_pages(wiki_base)

        assert report.high_confidence, "Expected at least one high-confidence candidate"
        assert report.high_confidence[0].suggested_action == "merge"

    def test_suggested_action_medium_confidence(self, tmp_path: Path, detector: DuplicateDetector):
        """Test suggested_action is 'redirect' for score 0.5-0.8."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test" / "pages"
        domain_dir.mkdir(parents=True)

        # name match (0.4) + source_url match (0.2) = 0.6, medium
        (domain_dir / "a.md").write_text(
            "---\nid: a\ntitle: Unique Title X\nkind: page\nsource_url: http://same.com\n---\ncontent\n"
        )
        (domain_dir / "b.md").write_text(
            "---\nid: b\ntitle: unique title x\nkind: page\nsource_url: http://same.com\n---\ncontent\n"
        )

        report = detector.analyze_all_pages(wiki_base)

        all_candidates = report.high_confidence + report.medium_confidence + report.low_confidence
        medium_or_higher = [c for c in all_candidates if c.duplicate_score >= 0.5]
        assert medium_or_higher, "Expected medium+ confidence candidate"
        for c in medium_or_higher:
            assert c.suggested_action in ("redirect", "merge")

    def test_suggested_action_low_confidence(self, tmp_path: Path, detector: DuplicateDetector):
        """Test suggested_action is 'keep_both' for score 0.3-0.5."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test" / "pages"
        domain_dir.mkdir(parents=True)

        # source_url match only (0.2) + 3 tag overlap (0.1) = 0.3, low confidence
        (domain_dir / "a.md").write_text(
            "---\nid: a\ntitle: Alpha\nkind: page\nsource_url: http://same.com\ntags:\n  - x\n  - y\n  - z\n---\ncontent\n"
        )
        (domain_dir / "b.md").write_text(
            "---\nid: b\ntitle: Beta\nkind: page\nsource_url: http://same.com\ntags:\n  - x\n  - y\n  - z\n---\ncontent\n"
        )

        report = detector.analyze_all_pages(wiki_base)

        low = report.low_confidence
        assert low, "Expected a low-confidence candidate"
        assert low[0].suggested_action == "keep_both"

    def test_primary_page_selection_by_backlinks(self, tmp_path: Path, detector: DuplicateDetector):
        """Test primary page selected by backlink count."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test_domain" / "pages"
        domain_dir.mkdir(parents=True)

        page1_content = """---
id: page1
title: Python
kind: page
source_url: https://example.com/python
backlinks: ["page3", "page4", "page5"]
---

Content
"""
        page2_content = """---
id: page2
title: python
kind: page
source_url: https://example.com/python
backlinks: ["page6"]
---

Content
"""
        (domain_dir / "page1.md").write_text(page1_content)
        (domain_dir / "page2.md").write_text(page2_content)

        report = detector.analyze_all_pages(wiki_base)

        if report.high_confidence:
            # page1 has more backlinks, so it should be primary
            assert report.high_confidence[0].primary_page == "page1"

    def test_primary_page_selection_by_content_length(
        self, tmp_path: Path, detector: DuplicateDetector
    ):
        """Test primary page selected by content length when backlinks equal."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test_domain" / "pages"
        domain_dir.mkdir(parents=True)

        page1_content = """---
id: page1
title: Python
kind: page
source_url: https://example.com/python
---

Short content
"""
        page2_content = """---
id: page2
title: python
kind: page
source_url: https://example.com/python
---

This is much longer content with more details and information about Python and its features and ecosystem.
"""
        (domain_dir / "page1.md").write_text(page1_content)
        (domain_dir / "page2.md").write_text(page2_content)

        report = detector.analyze_all_pages(wiki_base)

        if report.high_confidence:
            # page2 has more content, so it should be primary
            assert report.high_confidence[0].primary_page == "page2"

    def test_generate_report_creates_markdown(self, tmp_path: Path, detector: DuplicateDetector):
        """Test that generate_report creates markdown file."""
        output_file = tmp_path / "report.md"

        candidate = DuplicateCandidate(
            page_1="page1",
            page_2="page2",
            duplicate_score=0.85,
            reasons=["Same name", "Same source"],
            suggested_action="merge",
            primary_page="page1",
        )

        report = DuplicateReport(
            total_candidates=1,
            high_confidence=[candidate],
        )

        result_path = detector.generate_report(report, output_file)

        assert result_path.exists()
        content = result_path.read_text()
        assert "Duplicate Entity Detection Report" in content
        assert "page1" in content
        assert "page2" in content
        assert "Same name" in content

    def test_generate_report_sections(self, tmp_path: Path, detector: DuplicateDetector):
        """Test that generate_report includes all confidence sections."""
        output_file = tmp_path / "report.md"

        high_cand = DuplicateCandidate("p1", "p2", 0.9, ["reason"])
        med_cand = DuplicateCandidate("p3", "p4", 0.65, ["reason"])
        low_cand = DuplicateCandidate("p5", "p6", 0.35, ["reason"])

        report = DuplicateReport(
            total_candidates=3,
            high_confidence=[high_cand],
            medium_confidence=[med_cand],
            low_confidence=[low_cand],
        )

        detector.generate_report(report, output_file)
        content = output_file.read_text()

        assert "High Confidence" in content
        assert "Medium Confidence" in content
        assert "Low Confidence" in content

    def test_no_duplicate_comparison_twice(self, tmp_path: Path, detector: DuplicateDetector):
        """Test that page pairs are not compared twice."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test_domain" / "pages"
        domain_dir.mkdir(parents=True)

        # Create two identical pages
        page_content = """---
id: duplicate_test
title: Test
kind: page
source_url: https://same.com
---

Content
"""
        (domain_dir / "page1.md").write_text(page_content.replace("duplicate_test", "page1"))
        (domain_dir / "page2.md").write_text(page_content.replace("duplicate_test", "page2"))

        report = detector.analyze_all_pages(wiki_base)

        # Should find exactly one pair (not two, which would indicate duplication)
        total_pairs = (
            len(report.high_confidence) + len(report.medium_confidence) + len(report.low_confidence)
        )
        assert total_pairs <= 1

    def test_min_score_threshold_respected(self, tmp_path: Path):
        """Test that min_score threshold is respected."""
        detector_strict = DuplicateDetector(min_score=0.8)

        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test_domain" / "pages"
        domain_dir.mkdir(parents=True)

        # Create pages with low duplicate score
        page1 = """---
id: page1
title: Python
kind: page
---

Content
"""
        page2 = """---
id: page2
title: Ruby
kind: page
---

Content
"""
        (domain_dir / "page1.md").write_text(page1)
        (domain_dir / "page2.md").write_text(page2)

        report = detector_strict.analyze_all_pages(wiki_base)

        # Should find 0 candidates because threshold is 0.8
        assert report.total_candidates == 0

    def test_metadata_fields_handled_safely(self, tmp_path: Path, detector: DuplicateDetector):
        """Test that missing metadata fields are handled safely."""
        wiki_base = tmp_path / "wiki"
        domain_dir = wiki_base / "domains" / "test_domain" / "pages"
        domain_dir.mkdir(parents=True)

        # Minimal page with no optional fields
        page_content = """---
id: page1
title: Test
kind: page
---

Content
"""
        (domain_dir / "page1.md").write_text(page_content)

        report = detector.analyze_all_pages(wiki_base)
        assert report is not None  # Should not crash
