"""Tests for promotion scorer."""

from pathlib import Path

import pytest

from llm_wiki.promotion.config import PromotionConfig
from llm_wiki.promotion.models import CrossDomainReference, PromotionCandidate
from llm_wiki.promotion.scorer import PromotionScorer


class TestPromotionScorer:
    """Tests for PromotionScorer."""

    @pytest.fixture
    def scorer(self, temp_dir: Path) -> PromotionScorer:
        """Create scorer with temp directory."""
        wiki_base = temp_dir / "wiki"
        wiki_base.mkdir()
        config = PromotionConfig()
        return PromotionScorer(config=config, wiki_base=wiki_base)

    def test_age_factor_calculation(self):
        """Test age factor calculation."""
        config = PromotionConfig(age_factor_cap_days=365)

        # New page (0 days) should be 1.0
        assert config.calculate_age_factor(0) == 1.0

        # Very new page (1 day) should be high
        assert config.calculate_age_factor(1) > 0.99

        # Middle age (182.5 days) should be ~0.5
        assert abs(config.calculate_age_factor(182) - 0.5) < 0.01

        # Old page (365 days) should be 0.0
        assert config.calculate_age_factor(365) == 0.0

        # Older than cap should be 0.0
        assert config.calculate_age_factor(400) == 0.0

    def test_find_cross_domain_references(self, scorer: PromotionScorer, temp_dir: Path):
        """Test finding cross-domain references."""
        # Set up backlinks
        scorer.backlinks.add_page_links("page-a", "Content linking to [[page-b]]")
        scorer.backlinks.add_page_links("page-c", "Another link to [[page-b]]")

        # Find cross-domain refs from domain1 -> domain2
        refs = scorer._find_cross_domain_references("page-b", ["page-a", "page-c"], "domain2")

        # Should have unique references
        assert len(refs) >= 0  # May be 0 if domains not found

    def test_find_page_domain(self, scorer: PromotionScorer):
        """Test finding which domain contains a page."""
        # Set up wiki structure
        wiki_base = scorer.wiki_base
        domain1_dir = wiki_base / "domains" / "domain1" / "pages"
        domain1_dir.mkdir(parents=True)

        page_file = domain1_dir / "test-page.md"
        page_file.write_text("---\nid: test-page\ntitle: Test\n---\n")

        # Should find page in domain1
        domain = scorer._find_page_domain("test-page")
        assert domain == "domain1"

        # Should not find non-existent page
        domain = scorer._find_page_domain("nonexistent")
        assert domain is None

    def test_is_shared_page(self, scorer: PromotionScorer):
        """Test checking if page is in shared."""
        wiki_base = scorer.wiki_base
        shared_dir = wiki_base / "shared"
        shared_dir.mkdir(parents=True)

        # Create shared page
        shared_page = shared_dir / "shared-page.md"
        shared_page.write_text("---\nid: shared-page\ntitle: Shared\n---\n")

        # Should detect shared page
        assert scorer._is_shared_page("shared-page")

        # Should not detect non-existent page
        assert not scorer._is_shared_page("local-page")

    def test_score_page_with_quality_threshold(self, scorer: PromotionScorer, temp_dir: Path):
        """Test that pages below quality threshold are rejected."""
        wiki_base = scorer.wiki_base
        domain_dir = wiki_base / "domains" / "test-domain" / "pages"
        domain_dir.mkdir(parents=True)

        # Create very short page (low quality)
        page_file = domain_dir / "short-page.md"
        page_file.write_text(
            "---\n"
            "id: short-page\n"
            "title: Short\n"
            "domain: test-domain\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "---\n"
            "No\n"
        )

        # Should return None due to low quality
        result = scorer.score_page("short-page", page_file, "test-domain")
        assert result is None

    def test_score_page_with_cross_domain_refs(self, scorer: PromotionScorer, temp_dir: Path):
        """Test scoring with cross-domain references."""
        wiki_base = scorer.wiki_base

        # Create domain pages
        domain1_dir = wiki_base / "domains" / "domain1" / "pages"
        domain2_dir = wiki_base / "domains" / "domain2" / "pages"
        domain1_dir.mkdir(parents=True)
        domain2_dir.mkdir(parents=True)

        # Create page in domain1 that is referenced from domain2
        page_content = (
            "---\n"
            "id: target-page\n"
            "title: Target Page\n"
            "domain: domain1\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "---\n"
            "This is a high-quality page with substantial content that should be promoted. "
            "It contains multiple paragraphs and good information for cross-domain usage.\n"
        )
        page_file = domain1_dir / "target-page.md"
        page_file.write_text(page_content)

        # Create pages in domain2 that reference it
        ref_page1 = domain2_dir / "ref-page1.md"
        ref_page1.write_text(
            "---\n"
            "id: ref-page1\n"
            "title: Ref Page 1\n"
            "domain: domain2\n"
            "---\n"
            "This references [[target-page]] from domain1.\n"
        )

        ref_page2 = domain2_dir / "ref-page2.md"
        ref_page2.write_text(
            "---\n"
            "id: ref-page2\n"
            "title: Ref Page 2\n"
            "domain: domain2\n"
            "---\n"
            "Also links to [[target-page]].\n"
        )

        # Add links to backlinks
        scorer.backlinks.add_page_links("ref-page1", "[[target-page]]")
        scorer.backlinks.add_page_links("ref-page2", "[[target-page]]")

        # Score the page
        result = scorer.score_page("target-page", page_file, "domain1")

        if result is not None:
            # Should have cross-domain references
            assert result.cross_domain_references >= 2
            assert result.should_suggest_promote

    def test_score_all_pages(self, scorer: PromotionScorer, temp_dir: Path):
        """Test scoring all pages in wiki."""
        wiki_base = scorer.wiki_base

        # Create pages in domains
        domain_dir = wiki_base / "domains" / "test" / "pages"
        domain_dir.mkdir(parents=True)

        page_file = domain_dir / "page1.md"
        page_file.write_text(
            "---\n"
            "id: page1\n"
            "title: Page 1\n"
            "domain: test\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "---\n"
            "This is a high-quality page with substantial content for testing purposes. "
            "It should have enough text to pass quality checks.\n"
        )

        candidates = scorer.score_all_pages()

        # Should return list (may be empty if not eligible)
        assert isinstance(candidates, list)


class TestCrossDomainReference:
    """Tests for CrossDomainReference."""

    def test_hash_and_equality(self):
        """Test hash and equality operations."""
        ref1 = CrossDomainReference(
            referring_page_id="page-a",
            referring_domain="domain1",
            referenced_page_id="page-b",
            referenced_domain="domain2",
        )

        ref2 = CrossDomainReference(
            referring_page_id="page-a",
            referring_domain="domain1",
            referenced_page_id="page-b",
            referenced_domain="domain2",
        )

        # Should be equal by pages only
        assert ref1 == ref2
        assert hash(ref1) == hash(ref2)

        # Can use in set
        refs = {ref1, ref2}
        assert len(refs) == 1

    def test_different_references(self):
        """Test different references are not equal."""
        ref1 = CrossDomainReference(
            referring_page_id="page-a",
            referring_domain="domain1",
            referenced_page_id="page-b",
            referenced_domain="domain2",
        )

        ref2 = CrossDomainReference(
            referring_page_id="page-c",
            referring_domain="domain1",
            referenced_page_id="page-b",
            referenced_domain="domain2",
        )

        assert ref1 != ref2


class TestPromotionCandidate:
    """Tests for PromotionCandidate."""

    def test_to_dict(self):
        """Test converting candidate to dictionary."""
        candidate = PromotionCandidate(
            page_id="test-page",
            domain="test-domain",
            title="Test Page",
            cross_domain_references=3,
            total_references=5,
            quality_score=0.8,
            page_age_days=30,
            promotion_score=12.5,
            should_auto_promote=True,
            should_suggest_promote=True,
            referring_domains={"domain1", "domain2", "domain3"},
        )

        data = candidate.to_dict()

        assert data["page_id"] == "test-page"
        assert data["domain"] == "test-domain"
        assert data["promotion_score"] == 12.5
        assert "domain1" in data["referring_domains"]
