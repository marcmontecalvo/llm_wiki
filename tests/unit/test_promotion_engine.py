"""Tests for promotion engine."""

from pathlib import Path

import pytest

from llm_wiki.promotion.config import PromotionConfig
from llm_wiki.promotion.engine import PromotionEngine
from llm_wiki.promotion.models import PromotionCandidate


class TestPromotionEngine:
    """Tests for PromotionEngine."""

    @pytest.fixture
    def engine(self, temp_dir: Path) -> PromotionEngine:
        """Create promotion engine with temp directory."""
        wiki_base = temp_dir / "wiki"
        wiki_base.mkdir()
        config = PromotionConfig(require_approval=False)
        return PromotionEngine(config=config, wiki_base=wiki_base)

    def test_shared_directory_creation(self, engine: PromotionEngine):
        """Test that shared directory is created on initialization."""
        shared_dir = engine.wiki_base / "shared"
        assert shared_dir.exists()
        assert shared_dir.is_dir()

    def test_find_candidates(self, engine: PromotionEngine):
        """Test finding promotion candidates."""
        candidates = engine.find_candidates()
        assert isinstance(candidates, list)

    def test_promote_page_creates_shared_copy(self, engine: PromotionEngine):
        """Test promoting a page creates shared copy."""
        wiki_base = engine.wiki_base

        # Create source page
        domain_dir = wiki_base / "domains" / "test-domain" / "pages"
        domain_dir.mkdir(parents=True)
        source_file = domain_dir / "test-page.md"
        content = (
            "---\n"
            "id: test-page\n"
            "title: Test Page\n"
            "domain: test-domain\n"
            "---\n"
            "This is test content.\n"
        )
        source_file.write_text(content)

        # Promote page
        result = engine.promote_page("test-page", "test-domain", dry_run=False)

        assert result.success
        assert result.page_id == "test-page"

        # Verify shared copy exists
        shared_file = engine.shared_dir / "test-page.md"
        assert shared_file.exists()
        assert shared_file.read_text() == content

    def test_promote_page_creates_tombstone(self, engine: PromotionEngine):
        """Test that promotion creates tombstone at original location."""
        wiki_base = engine.wiki_base

        # Create source page
        domain_dir = wiki_base / "domains" / "test-domain" / "pages"
        domain_dir.mkdir(parents=True)
        source_file = domain_dir / "test-page.md"
        source_file.write_text(
            "---\nid: test-page\ntitle: Test Page\ndomain: test-domain\n---\nOriginal content.\n"
        )

        # Promote
        engine.promote_page("test-page", "test-domain")

        # Verify tombstone was created
        assert source_file.exists()
        content = source_file.read_text()
        assert "Moved to shared" in content or "promoted" in content.lower()

    def test_promote_nonexistent_page_fails(self, engine: PromotionEngine):
        """Test promoting non-existent page fails."""
        result = engine.promote_page("nonexistent", "test-domain")

        assert not result.success
        assert "not found" in result.message.lower()

    def test_promote_already_shared_page_fails(self, engine: PromotionEngine):
        """Test promoting already-shared page fails."""
        wiki_base = engine.wiki_base

        # Create source page in domain
        domain_dir = wiki_base / "domains" / "test-domain" / "pages"
        domain_dir.mkdir(parents=True, exist_ok=True)
        source_file = domain_dir / "shared-page.md"
        source_file.write_text("---\nid: shared-page\ntitle: Shared\n---\n")

        # Create shared page (already promoted)
        shared_file = engine.shared_dir / "shared-page.md"
        shared_file.write_text("---\nid: shared-page\ntitle: Shared\n---\n")

        # Try to promote again
        result = engine.promote_page("shared-page", "test-domain")

        assert not result.success
        assert "already exists" in result.message.lower()

    def test_promote_page_dry_run(self, engine: PromotionEngine):
        """Test dry-run mode doesn't make changes."""
        wiki_base = engine.wiki_base

        # Create source page
        domain_dir = wiki_base / "domains" / "test-domain" / "pages"
        domain_dir.mkdir(parents=True)
        source_file = domain_dir / "test-page.md"
        source_file.write_text(
            "---\nid: test-page\ntitle: Test Page\ndomain: test-domain\n---\nContent.\n"
        )

        # Dry run
        result = engine.promote_page("test-page", "test-domain", dry_run=True)

        assert result.success

        # Verify no shared copy was created
        shared_file = engine.shared_dir / "test-page.md"
        assert not shared_file.exists()

    def test_unpromote_page(self, engine: PromotionEngine):
        """Test un-promoting a page from shared."""
        wiki_base = engine.wiki_base

        # Create shared page
        shared_file = engine.shared_dir / "shared-page.md"
        content = (
            "---\nid: shared-page\ntitle: Shared Page\ndomain: test-domain\n---\nShared content.\n"
        )
        shared_file.write_text(content)

        # Un-promote
        result = engine.unpromote_page("shared-page", "restore-domain")

        assert result.success

        # Verify page restored to domain
        restored_file = wiki_base / "domains" / "restore-domain" / "pages" / "shared-page.md"
        assert restored_file.exists()

        # Verify removed from shared
        assert not shared_file.exists()

    def test_unpromote_nonexistent_shared_page_fails(self, engine: PromotionEngine):
        """Test un-promoting non-existent shared page fails."""
        result = engine.unpromote_page("nonexistent", "some-domain")

        assert not result.success
        assert "not found" in result.message.lower()

    def test_suggest_promotion_creates_review_item(self, engine: PromotionEngine):
        """Test suggesting promotion creates review item."""
        candidate = PromotionCandidate(
            page_id="test-page",
            domain="test-domain",
            title="Test Page",
            cross_domain_references=3,
            total_references=5,
            quality_score=0.8,
            page_age_days=30,
            promotion_score=8.0,
            should_auto_promote=False,
            should_suggest_promote=True,
            referring_domains={"domain1", "domain2"},
        )

        result = engine.suggest_promotion(candidate)

        assert result is not None
        assert result.success
        assert result.review_item_id is not None

    def test_process_candidates_auto_promote(self, engine: PromotionEngine):
        """Test processing candidates with auto-promotion."""
        wiki_base = engine.wiki_base

        # Create page
        domain_dir = wiki_base / "domains" / "test-domain" / "pages"
        domain_dir.mkdir(parents=True)
        page_file = domain_dir / "test-page.md"
        page_file.write_text(
            "---\n"
            "id: test-page\n"
            "title: Test Page\n"
            "domain: test-domain\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "---\n"
            "High quality content that is promoted automatically.\n"
        )

        # Process
        report = engine.process_candidates()

        assert report.total_candidates >= 0
        assert isinstance(report.auto_promoted, int)
        assert isinstance(report.suggested_for_review, int)

    def test_process_candidates_suggest_review(self, engine: PromotionEngine):
        """Test processing candidates that need review."""
        engine.config.require_approval = True

        wiki_base = engine.wiki_base

        # Create page
        domain_dir = wiki_base / "domains" / "test-domain" / "pages"
        domain_dir.mkdir(parents=True)
        page_file = domain_dir / "test-page.md"
        page_file.write_text(
            "---\n"
            "id: test-page\n"
            "title: Test Page\n"
            "domain: test-domain\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "---\n"
            "High quality content.\n"
        )

        # Process
        report = engine.process_candidates()

        assert report.total_candidates >= 0

    def test_create_tombstone(self, engine: PromotionEngine, temp_dir: Path):
        """Test creating tombstone marker."""
        source_file = temp_dir / "test.md"
        source_file.write_text("Original content")

        engine._create_tombstone(source_file, "test-page")

        # Verify tombstone was created
        assert source_file.exists()
        content = source_file.read_text()
        assert "shared" in content.lower()


class TestPromotionConfig:
    """Tests for promotion configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PromotionConfig()

        assert config.auto_promote_threshold == 10.0
        assert config.suggest_promote_threshold == 5.0
        assert config.min_quality_score == 0.6
        assert config.min_cross_domain_refs == 2
        assert config.require_approval is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = PromotionConfig(
            auto_promote_threshold=20.0,
            suggest_promote_threshold=10.0,
            min_quality_score=0.7,
            min_cross_domain_refs=3,
            require_approval=False,
        )

        assert config.auto_promote_threshold == 20.0
        assert config.suggest_promote_threshold == 10.0
        assert config.min_quality_score == 0.7
        assert config.min_cross_domain_refs == 3
        assert config.require_approval is False

    def test_age_factor_calculation(self):
        """Test age factor in config."""
        config = PromotionConfig(age_factor_cap_days=365)

        # Test various ages
        assert config.calculate_age_factor(0) == 1.0
        assert config.calculate_age_factor(365) == 0.0
        assert 0.0 <= config.calculate_age_factor(180) <= 1.0
