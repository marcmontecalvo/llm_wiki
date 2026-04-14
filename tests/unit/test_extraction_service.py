"""Tests for content extraction service."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from llm_wiki.extraction.service import ContentExtractor, ExtractionError


class TestContentExtractor:
    """Tests for ContentExtractor."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock LLM client."""
        return Mock()

    @pytest.fixture
    def extractor(self, mock_client: Mock) -> ContentExtractor:
        """Create content extractor with mock client."""
        return ContentExtractor(client=mock_client)

    def test_extract_page_kind_entity(self, extractor: ContentExtractor, mock_client: Mock):
        """Test extracting entity kind."""
        mock_client.chat_completion.return_value = "entity"

        content = "# John Doe\n\nSoftware engineer at TechCorp."
        metadata = {"title": "John Doe"}

        kind = extractor.extract_page_kind(content, metadata)

        assert kind == "entity"
        mock_client.chat_completion.assert_called_once()

    def test_extract_page_kind_concept(self, extractor: ContentExtractor, mock_client: Mock):
        """Test extracting concept kind."""
        mock_client.chat_completion.return_value = "concept"

        content = "# Microservices\n\nArchitectural pattern for distributed systems."
        metadata = {"title": "Microservices"}

        kind = extractor.extract_page_kind(content, metadata)

        assert kind == "concept"

    def test_extract_page_kind_page(self, extractor: ContentExtractor, mock_client: Mock):
        """Test extracting general page kind."""
        mock_client.chat_completion.return_value = "page"

        content = "# Meeting Notes\n\nDiscussed project timeline."
        metadata = {"title": "Meeting Notes"}

        kind = extractor.extract_page_kind(content, metadata)

        assert kind == "page"

    def test_extract_page_kind_uses_existing(self, extractor: ContentExtractor, mock_client: Mock):
        """Test that existing kind is preserved."""
        content = "Content"
        metadata = {"title": "Test", "kind": "entity"}

        kind = extractor.extract_page_kind(content, metadata)

        # Should not call LLM if kind already set
        assert kind == "entity"
        mock_client.chat_completion.assert_not_called()

    def test_extract_page_kind_ignores_source(self, extractor: ContentExtractor, mock_client: Mock):
        """Test that source kind is re-evaluated."""
        mock_client.chat_completion.return_value = "entity"

        content = "# Test\n\nContent"
        metadata = {"title": "Test", "kind": "source"}

        kind = extractor.extract_page_kind(content, metadata)

        # Should call LLM to determine real kind
        assert kind == "entity"
        mock_client.chat_completion.assert_called_once()

    def test_extract_page_kind_invalid_response(
        self, extractor: ContentExtractor, mock_client: Mock
    ):
        """Test handling invalid kind response."""
        mock_client.chat_completion.return_value = "invalid"

        content = "Content"
        metadata = {"title": "Test"}

        kind = extractor.extract_page_kind(content, metadata)

        # Should default to "page"
        assert kind == "page"

    def test_extract_page_kind_error(self, extractor: ContentExtractor, mock_client: Mock):
        """Test error handling in kind extraction."""
        mock_client.chat_completion.side_effect = Exception("API error")

        content = "Content"
        metadata = {"title": "Test"}

        with pytest.raises(ExtractionError, match="Failed to extract page kind"):
            extractor.extract_page_kind(content, metadata)

    def test_extract_tags_from_content(self, extractor: ContentExtractor, mock_client: Mock):
        """Test extracting tags from content."""
        mock_client.chat_completion.return_value = '["python", "api", "rest"]'

        content = "# REST API in Python\n\nBuilding RESTful APIs with Flask."
        metadata = {"title": "REST API"}

        tags = extractor.extract_tags(content, metadata)

        assert tags == ["python", "api", "rest"]
        # Should pass response_format for JSON
        call_args = mock_client.chat_completion.call_args
        assert call_args[1]["response_format"] == {"type": "json_object"}

    def test_extract_tags_uses_existing(self, extractor: ContentExtractor, mock_client: Mock):
        """Test that existing tags are preserved."""
        content = "Content"
        metadata = {"title": "Test", "tags": ["existing", "tags"]}

        tags = extractor.extract_tags(content, metadata)

        # Should not call LLM if tags already exist
        assert tags == ["existing", "tags"]
        mock_client.chat_completion.assert_not_called()

    def test_extract_tags_object_format(self, extractor: ContentExtractor, mock_client: Mock):
        """Test extracting tags from JSON object format."""
        mock_client.chat_completion.return_value = '{"tags": ["tag1", "tag2"]}'

        content = "Content"
        metadata = {"title": "Test"}

        tags = extractor.extract_tags(content, metadata)

        assert tags == ["tag1", "tag2"]

    def test_extract_tags_max_count(self, extractor: ContentExtractor, mock_client: Mock):
        """Test that tags are limited to 5."""
        mock_client.chat_completion.return_value = '["t1", "t2", "t3", "t4", "t5", "t6"]'

        content = "Content"
        metadata = {"title": "Test"}

        tags = extractor.extract_tags(content, metadata)

        assert len(tags) == 5

    def test_extract_tags_error_returns_empty(self, extractor: ContentExtractor, mock_client: Mock):
        """Test that tag extraction errors don't fail completely."""
        mock_client.chat_completion.side_effect = Exception("API error")

        content = "Content"
        metadata = {"title": "Test"}

        tags = extractor.extract_tags(content, metadata)

        # Should return empty list, not raise
        assert tags == []

    def test_extract_summary_from_content(self, extractor: ContentExtractor, mock_client: Mock):
        """Test extracting summary from content."""
        mock_client.chat_completion.return_value = "A concise summary of the content."

        content = "# Title\n\nLong content here with lots of details."
        metadata = {"title": "Title"}

        summary = extractor.extract_summary(content, metadata)

        assert summary == "A concise summary of the content."

    def test_extract_summary_uses_existing(self, extractor: ContentExtractor, mock_client: Mock):
        """Test that existing summary is preserved."""
        content = "Content"
        metadata = {"title": "Test", "summary": "Existing summary"}

        summary = extractor.extract_summary(content, metadata)

        assert summary == "Existing summary"
        mock_client.chat_completion.assert_not_called()

    def test_extract_summary_truncates_long_response(
        self, extractor: ContentExtractor, mock_client: Mock
    ):
        """Test that long summaries are truncated."""
        mock_client.chat_completion.return_value = "a" * 300

        content = "Content"
        metadata = {"title": "Test"}

        summary = extractor.extract_summary(content, metadata, max_length=200)

        assert len(summary) == 200
        assert summary.endswith("...")

    def test_extract_summary_error_returns_fallback(
        self, extractor: ContentExtractor, mock_client: Mock
    ):
        """Test that summary extraction errors return fallback."""
        mock_client.chat_completion.side_effect = Exception("API error")

        content = "This is the content that will be used as fallback."
        metadata = {"title": "Test"}

        summary = extractor.extract_summary(content, metadata, max_length=50)

        # Should use content as fallback
        assert len(summary) <= 50
        assert "This is the content" in summary

    def test_extract_metadata_full_workflow(
        self, extractor: ContentExtractor, mock_client: Mock, temp_dir: Path
    ):
        """Test full metadata extraction workflow."""
        # Create test file
        test_file = temp_dir / "test.md"
        test_file.write_text(
            """---
title: Test Page
domain: general
---

# Test Content

This is the content of the test page.
"""
        )

        # Mock LLM responses
        responses = ["entity", '["tag1", "tag2"]', "This is a summary."]
        mock_client.chat_completion.side_effect = responses

        metadata = extractor.extract_metadata(test_file)

        # Should have extracted all fields
        assert metadata["kind"] == "entity"
        assert metadata["tags"] == ["tag1", "tag2"]
        assert metadata["summary"] == "This is a summary."

        # Should preserve existing fields
        assert metadata["title"] == "Test Page"
        assert metadata["domain"] == "general"

    def test_extract_metadata_preserves_existing_fields(
        self, extractor: ContentExtractor, mock_client: Mock, temp_dir: Path
    ):
        """Test that existing metadata fields are preserved."""
        test_file = temp_dir / "test.md"
        test_file.write_text(
            """---
title: Test
kind: concept
tags:
  - existing
summary: Existing summary
---

Content here.
"""
        )

        metadata = extractor.extract_metadata(test_file)

        # Should preserve all existing fields
        assert metadata["kind"] == "concept"
        assert metadata["tags"] == ["existing"]
        assert metadata["summary"] == "Existing summary"

        # Should not have called LLM for any of these
        mock_client.chat_completion.assert_not_called()

    def test_extract_metadata_error(
        self, extractor: ContentExtractor, mock_client: Mock, temp_dir: Path
    ):
        """Test error handling in metadata extraction."""
        test_file = temp_dir / "test.md"
        test_file.write_text("---\ntitle: Test\n---\nContent")

        # Make kind extraction fail
        mock_client.chat_completion.side_effect = Exception("API error")

        with pytest.raises(ExtractionError, match="Failed to extract metadata"):
            extractor.extract_metadata(test_file)
