"""Tests for normalization pipeline."""

from pathlib import Path

import pytest

from llm_wiki.adapters.base import AdapterRegistry
from llm_wiki.adapters.markdown import MarkdownAdapter
from llm_wiki.adapters.text import TextAdapter
from llm_wiki.ingest.normalizer import NormalizationPipeline


class TestNormalizationPipeline:
    """Tests for NormalizationPipeline."""

    @pytest.fixture
    def adapter_registry(self) -> AdapterRegistry:
        """Create adapter registry with standard adapters."""
        registry = AdapterRegistry()
        registry.register(MarkdownAdapter)
        registry.register(TextAdapter)
        return registry

    @pytest.fixture
    def pipeline(self, adapter_registry: AdapterRegistry, temp_dir: Path) -> NormalizationPipeline:
        """Create normalization pipeline."""
        # Use temp_dir as base to avoid config issues
        config_dir = Path("config")  # Use real config for routing/domains
        return NormalizationPipeline(adapter_registry, config_dir)

    def test_process_markdown_file(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test processing markdown file through pipeline."""
        # Create test markdown file
        test_file = temp_dir / "test-doc.md"
        test_file.write_text(
            """---
title: Test Document
---

# Hello

This is content.
"""
        )

        # Process file
        output_path = pipeline.process_file(test_file)

        # Verify output exists
        assert output_path.exists()
        assert output_path.parent.name == "queue"

        # Read output
        content = output_path.read_text()

        # Should have frontmatter with generated fields
        assert "id:" in content
        assert "domain:" in content
        assert "status: queued" in content
        assert "title: Test Document" in content

        # Should have body content
        assert "# Hello" in content
        assert "This is content." in content

    def test_process_text_file(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test processing text file through pipeline."""
        # Create test text file
        test_file = temp_dir / "my-notes.txt"
        test_file.write_text(
            """My Notes
These are my notes.
More content here.
"""
        )

        # Process file
        output_path = pipeline.process_file(test_file)

        # Verify output exists
        assert output_path.exists()

        # Read output
        content = output_path.read_text()

        # Should have frontmatter
        assert "id:" in content
        assert "title: My Notes" in content
        assert "source_type: text" in content

        # Should have normalized markdown body
        assert "# My Notes" in content
        assert "These are my notes." in content

    def test_determine_domain_explicit(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test domain determination from explicit frontmatter."""
        test_file = temp_dir / "test.md"
        test_file.write_text(
            """---
domain: homelab
---

Test content.
"""
        )

        output_path = pipeline.process_file(test_file)
        content = output_path.read_text()

        # Should use explicit domain
        assert "domain: homelab" in content
        assert "homelab" in str(output_path)

    def test_determine_domain_routing_rule(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test domain determination from routing rules."""
        # Create file with path matching routing rule
        test_file = temp_dir / "proxmox-notes.md"
        test_file.write_text("# Proxmox Notes\n\nContent here.")

        output_path = pipeline.process_file(test_file)
        content = output_path.read_text()

        # Should match "proxmox" rule → homelab domain
        assert "domain: homelab" in content

    def test_determine_domain_fallback(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test domain determination falls back to default."""
        test_file = temp_dir / "random-file.md"
        test_file.write_text("# Random Content\n\nNo specific domain.")

        output_path = pipeline.process_file(test_file)
        content = output_path.read_text()

        # Should fall back to "general" domain
        assert "domain: general" in content

    def test_determine_domain_invalid_explicit(
        self, pipeline: NormalizationPipeline, temp_dir: Path
    ):
        """Test invalid explicit domain falls back to routing."""
        test_file = temp_dir / "test.md"
        test_file.write_text(
            """---
domain: nonexistent-domain
---

Test content.
"""
        )

        output_path = pipeline.process_file(test_file)
        content = output_path.read_text()

        # Should fall back to general (since no routing rule matches)
        assert "domain: general" in content

    def test_page_id_generation(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test page ID is generated correctly."""
        test_file = temp_dir / "my-test-page.md"
        test_file.write_text(
            """---
title: My Test Page
---

Content.
"""
        )

        output_path = pipeline.process_file(test_file)
        content = output_path.read_text()

        # ID should be based on title + domain (domain-prefixed)
        assert "id: general-my-test-page" in content
        assert output_path.stem == "general-my-test-page"

    def test_queue_directory_created(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test queue directory is created if it doesn't exist."""
        test_file = temp_dir / "test.md"
        test_file.write_text("# Test\n\nContent.")

        # Ensure queue doesn't exist yet
        queue_dir = Path("wiki_system/domains/general/queue")
        if queue_dir.exists():
            # Clean up if exists from previous test
            for f in queue_dir.glob("*.md"):
                f.unlink()

        output_path = pipeline.process_file(test_file)

        # Queue directory should now exist
        assert output_path.parent.exists()
        assert output_path.parent.name == "queue"

    def test_metadata_preserved(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test original metadata is preserved in output."""
        test_file = temp_dir / "test.md"
        test_file.write_text(
            """---
title: Test
author: John Doe
tags:
  - test
  - example
---

Content.
"""
        )

        output_path = pipeline.process_file(test_file)
        content = output_path.read_text()

        # Original metadata should be preserved
        assert "author: John Doe" in content
        assert "tags:" in content
        assert "- test" in content
        assert "- example" in content

    def test_no_adapter_found(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test error when no adapter can handle file."""
        test_file = temp_dir / "test.pdf"
        test_file.write_bytes(b"fake pdf content")

        with pytest.raises(ValueError, match="No adapter found"):
            pipeline.process_file(test_file)

    def test_status_field_added(self, pipeline: NormalizationPipeline, temp_dir: Path):
        """Test status field is added to frontmatter."""
        test_file = temp_dir / "test.md"
        test_file.write_text("# Test\n\nContent.")

        output_path = pipeline.process_file(test_file)
        content = output_path.read_text()

        # Status should be "queued"
        assert "status: queued" in content

    def test_multiple_files_different_domains(
        self, pipeline: NormalizationPipeline, temp_dir: Path
    ):
        """Test processing multiple files to different domains."""
        # File for homelab domain
        homelab_file = temp_dir / "proxmox.md"
        homelab_file.write_text("# Proxmox Notes\n\nContent.")

        # File for home-assistant domain
        ha_file = temp_dir / "home-assistant.md"
        ha_file.write_text("# Home Assistant\n\nContent.")

        # Process both
        homelab_output = pipeline.process_file(homelab_file)
        ha_output = pipeline.process_file(ha_file)

        # Should be in different domain queues
        assert "homelab" in str(homelab_output)
        assert "home-assistant" in str(ha_output)
        assert homelab_output.parent != ha_output.parent
