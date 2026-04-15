"""Tests for extraction pipeline."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from llm_wiki.extraction.pipeline import ExtractionPipeline


class TestExtractionPipeline:
    """Tests for ExtractionPipeline."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock LLM client."""
        return Mock()

    @pytest.fixture
    def pipeline(self, mock_client: Mock, temp_dir: Path) -> ExtractionPipeline:
        """Create extraction pipeline with mocks."""
        wiki_base = temp_dir / "wiki_system"
        wiki_base.mkdir()

        return ExtractionPipeline(
            wiki_base=wiki_base,
            config_dir=Path("config"),
            client=mock_client,
        )

    def test_process_queue_empty(self, pipeline: ExtractionPipeline):
        """Test processing empty queue."""
        stats = pipeline.process_queue("general")

        assert stats["processed"] == 0
        assert stats["failed"] == 0

    def test_process_queue_success(
        self, pipeline: ExtractionPipeline, mock_client: Mock, temp_dir: Path
    ):
        """Test processing queue with files."""
        # Create queue with test file
        queue_dir = temp_dir / "wiki_system/domains/general/queue"
        queue_dir.mkdir(parents=True)

        test_file = queue_dir / "test-page.md"
        test_file.write_text(
            """---
title: Test Page
kind: page
---

# Test Content
"""
        )

        # Mock LLM responses
        mock_client.chat_completion.side_effect = [
            "page",  # kind
            '["test"]',  # tags
            "A test page",  # summary
        ]

        # Process queue
        stats = pipeline.process_queue("general")

        assert stats["processed"] == 1
        assert stats["failed"] == 0

        # File should be moved to pages/
        pages_dir = temp_dir / "wiki_system/domains/general/pages"
        assert pages_dir.exists()
        assert (pages_dir / "test-page.md").exists()
        assert not test_file.exists()  # Moved from queue

    def test_process_queue_with_entity_extraction(
        self, pipeline: ExtractionPipeline, mock_client: Mock, temp_dir: Path
    ):
        """Test processing entity page extracts entities."""
        queue_dir = temp_dir / "wiki_system/domains/general/queue"
        queue_dir.mkdir(parents=True)

        test_file = queue_dir / "entity.md"
        test_file.write_text("---\ntitle: Python\n---\nContent")

        # Mock responses: kind, tags, summary, entities
        mock_client.chat_completion.side_effect = [
            "entity",  # kind
            '["programming"]',  # tags
            "Programming language",  # summary
            '{"entities": [{"name": "Python", "type": "technology", "description": "Language"}]}',  # entities
        ]

        stats = pipeline.process_queue("general")

        assert stats["processed"] == 1

        # Check enriched file
        enriched = temp_dir / "wiki_system/domains/general/pages/entity.md"
        content = enriched.read_text()

        assert "entities:" in content
        assert "Python" in content

    def test_process_queue_handles_errors(
        self, pipeline: ExtractionPipeline, mock_client: Mock, temp_dir: Path
    ):
        """Test error handling in queue processing."""
        queue_dir = temp_dir / "wiki_system/domains/general/queue"
        queue_dir.mkdir(parents=True)

        test_file = queue_dir / "bad.md"
        test_file.write_text("---\ntitle: Test\n---\nContent")

        # Mock error
        mock_client.chat_completion.side_effect = Exception("API error")

        stats = pipeline.process_queue("general")

        assert stats["processed"] == 0
        assert stats["failed"] == 1

    def test_process_all_queues(
        self, pipeline: ExtractionPipeline, mock_client: Mock, temp_dir: Path
    ):
        """Test processing all domain queues."""
        # Create multiple domains with queues
        for domain in ["general", "homelab"]:
            queue_dir = temp_dir / f"wiki_system/domains/{domain}/queue"
            queue_dir.mkdir(parents=True)

            test_file = queue_dir / f"{domain}.md"
            test_file.write_text(f"---\ntitle: {domain}\n---\nContent")

        # Mock responses for both files
        mock_client.chat_completion.side_effect = [
            "page",
            '["test"]',
            "Summary",  # general
            "page",
            '["test"]',
            "Summary",  # homelab
        ]

        results = pipeline.process_all_queues()

        assert "general" in results
        assert "homelab" in results
        assert results["general"]["processed"] == 1
        assert results["homelab"]["processed"] == 1

    def test_process_file_with_concept(
        self, pipeline: ExtractionPipeline, mock_client: Mock, temp_dir: Path
    ):
        """Test processing concept page extracts concepts."""
        queue_dir = temp_dir / "wiki_system/domains/general/queue"
        queue_dir.mkdir(parents=True)

        test_file = queue_dir / "concept.md"
        test_file.write_text("---\ntitle: Microservices\n---\nContent")

        # Mock responses: kind, tags, summary, concepts
        mock_client.chat_completion.side_effect = [
            "concept",
            '["architecture"]',
            "Architectural pattern",
            '{"concepts": [{"name": "Service independence", "description": "Each service runs independently"}]}',
        ]

        stats = pipeline.process_queue("general")

        assert stats["processed"] == 1

        enriched = temp_dir / "wiki_system/domains/general/pages/concept.md"
        content = enriched.read_text()

        assert "concepts:" in content
        assert "Service independence" in content

    def test_process_file_updates_backlink_index(
        self, pipeline: ExtractionPipeline, mock_client: Mock, temp_dir: Path
    ):
        """Test that processing a file updates the backlink index."""
        queue_dir = temp_dir / "wiki_system/domains/general/queue"
        queue_dir.mkdir(parents=True)

        test_file = queue_dir / "my-page.md"
        test_file.write_text(
            """---
id: my-page
title: My Page
---

Links to [[other-page]] and [[another-page]].
"""
        )

        mock_client.chat_completion.side_effect = [
            "page",
            '["test"]',
            "A test page",
        ]

        pipeline.process_queue("general")

        # Backlink index should have the forward links recorded
        forward_links = pipeline.backlinks.get_forward_links("my-page")
        assert "other-page" in forward_links
        assert "another-page" in forward_links

        # Targets should have my-page as a backlink
        assert "my-page" in pipeline.backlinks.get_backlinks("other-page")
        assert "my-page" in pipeline.backlinks.get_backlinks("another-page")

    def test_process_file_saves_backlink_index(
        self, pipeline: ExtractionPipeline, mock_client: Mock, temp_dir: Path
    ):
        """Test that backlink index is persisted after processing."""
        queue_dir = temp_dir / "wiki_system/domains/general/queue"
        queue_dir.mkdir(parents=True)

        test_file = queue_dir / "page-a.md"
        test_file.write_text("---\nid: page-a\ntitle: Page A\n---\n\nLinks to [[page-b]].\n")

        mock_client.chat_completion.side_effect = ["page", '["test"]', "Summary"]

        pipeline.process_queue("general")

        # Index file should be written to disk
        index_file = temp_dir / "wiki_system" / "index" / "backlinks.json"
        assert index_file.exists()

        # Load a fresh index and verify data persisted
        from llm_wiki.index.backlinks import BacklinkIndex

        fresh_index = BacklinkIndex(index_dir=temp_dir / "wiki_system" / "index")
        fresh_index.load()
        assert "page-b" in fresh_index.get_forward_links("page-a")
