"""Integration tests for backlink tracking flow."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from llm_wiki.daemon.jobs.governance import GovernanceJob
from llm_wiki.extraction.pipeline import ExtractionPipeline
from llm_wiki.index.backlinks import BacklinkIndex


class TestBacklinkFlow:
    """Integration tests for complete backlink tracking flow."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock LLM client."""
        client = Mock()
        client.chat_completion.side_effect = [
            "page",  # kind classification
            '["wiki"]',  # tags
            "A test page",  # summary
        ] * 10  # enough for multiple calls
        return client

    @pytest.fixture
    def wiki_base(self, temp_dir: Path) -> Path:
        """Set up a wiki for testing backlink flow.

        Returns:
            Path to wiki base directory
        """
        wiki_base = temp_dir / "wiki"
        wiki_base.mkdir()

        # Create domain with pages and queue directories
        domain_dir = wiki_base / "domains" / "general"
        (domain_dir / "pages").mkdir(parents=True)
        (domain_dir / "queue").mkdir(parents=True)
        (wiki_base / "index").mkdir(parents=True)
        (wiki_base / "reports").mkdir(parents=True)

        return wiki_base

    def test_extraction_updates_backlinks(self, wiki_base: Path, mock_client):
        """Test that extraction pipeline updates backlink index."""
        # Create a queued page with links
        queue_file = wiki_base / "domains" / "general" / "queue" / "page-a.md"
        queue_file.write_text(
            "---\n"
            "id: page-a\n"
            "title: Page A\n"
            "kind: page\n"
            "---\n"
            "This page links to [[page-b]] and [[page-c]]."
        )

        # Process the queue
        pipeline = ExtractionPipeline(
            wiki_base=wiki_base,
            config_dir=Path("config"),
            client=mock_client,
        )
        pipeline.process_queue("general")

        # Verify backlink index was updated
        index = BacklinkIndex(index_dir=wiki_base / "index")
        index.load()

        # page-a should have forward links to page-b and page-c
        forward = index.get_forward_links("page-a")
        assert "page-b" in forward
        assert "page-c" in forward

        # page-b and page-c should have page-a as backlink
        assert "page-a" in index.get_backlinks("page-b")
        assert "page-a" in index.get_backlinks("page-c")

    def test_governance_detects_broken_links(self, wiki_base: Path):
        """Test that governance job detects and reports broken links."""
        # Create pages with a broken link
        pages_dir = wiki_base / "domains" / "general" / "pages"
        page_with_broken = pages_dir / "page-broken.md"
        page_with_broken.write_text(
            "---\n"
            "id: page-broken\n"
            "title: Page With Broken Link\n"
            "kind: page\n"
            "---\n"
            "This links to [[nonexistent-target]]."
        )

        # Create a backlink index
        index = BacklinkIndex(index_dir=wiki_base / "index")
        index.add_page_links("page-broken", "This links to [[nonexistent-target]].")
        index.save()

        # Run governance
        job = GovernanceJob(wiki_base=wiki_base, client=None)
        stats = job.execute()

        # Verify broken links are detected
        assert stats["broken_links"] == 1
        assert stats["orphan_pages"] == 1  # page-broken has no backlinks

    def test_governance_reports_orphans(self, wiki_base: Path):
        """Test that governance report includes orphan pages."""
        # Create an orphan page (no links to it)
        pages_dir = wiki_base / "domains" / "general" / "pages"
        orphan_page = pages_dir / "orphan-page.md"
        orphan_page.write_text(
            "---\n"
            "id: orphan-page\n"
            "title: Orphan Page\n"
            "kind: page\n"
            "---\n"
            "This page has no incoming links."
        )

        # Create another page that links TO the orphan
        linked_page = pages_dir / "linked-page.md"
        linked_page.write_text(
            "---\n"
            "id: linked-page\n"
            "title: Linked Page\n"
            "kind: page\n"
            "---\n"
            "This links to [[orphan-page]]."
        )

        # Build backlink index
        index = BacklinkIndex(index_dir=wiki_base / "index")
        index.add_page_links("orphan-page", "This page has no incoming links.")
        index.add_page_links("linked-page", "This links to [[orphan-page]].")
        index.update_broken_links({"orphan-page", "linked-page"})
        index.save()

        # Run governance
        job = GovernanceJob(wiki_base=wiki_base, client=None)
        stats = job.execute()

        # orphan-page should NOT be in orphan_pages (it has a backlink)
        # linked-page should NOT be in orphan_pages (it has no backlinks... wait, it has)
        # Actually linked-page has no incoming links, so it should be orphan
        assert stats["orphan_pages"] >= 1

    def test_full_flow_ingest_to_governance(self, wiki_base: Path, mock_client):
        """Test complete flow: queue page → extract → governance report."""
        # 1. Queue a page with links
        queue_file = wiki_base / "domains" / "general" / "queue" / "test-page.md"
        queue_file.write_text(
            "---\n"
            "id: test-page\n"
            "title: Test Page\n"
            "kind: page\n"
            "---\n"
            "Links to [[target-1]] and [[target-2]]."
        )

        # 2. Run extraction pipeline
        pipeline = ExtractionPipeline(
            wiki_base=wiki_base,
            config_dir=Path("config"),
            client=mock_client,
        )
        pipeline.process_queue("general")

        # 3. Verify backlinks are indexed
        index = BacklinkIndex(index_dir=wiki_base / "index")
        index.load()
        assert index.get_forward_links("test-page") == ["target-1", "target-2"]

        # 4. Run governance (should detect broken links since targets don't exist)
        job = GovernanceJob(wiki_base=wiki_base, client=None)
        stats = job.execute()

        # 5. Verify broken links reported
        assert stats["broken_links"] == 2  # target-1 and target-2 don't exist

        # 6. Verify index was persisted after governance
        index2 = BacklinkIndex(index_dir=wiki_base / "index")
        index2.load()
        # Broken links should be saved in the index
        broken = index2.get_broken_links("test-page")
        assert "target-1" in broken
        assert "target-2" in broken
