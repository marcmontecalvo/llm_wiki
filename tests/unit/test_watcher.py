"""Tests for inbox watcher."""

from pathlib import Path

import pytest

from llm_wiki.ingest.watcher import InboxWatcher


class TestInboxWatcher:
    """Tests for InboxWatcher."""

    @pytest.fixture
    def inbox_dir(self, temp_dir: Path) -> Path:
        """Create test inbox directory."""
        inbox = temp_dir / "inbox"
        inbox.mkdir()
        return inbox

    @pytest.fixture
    def watcher(self, inbox_dir: Path) -> InboxWatcher:
        """Create inbox watcher with test directories."""
        config_dir = Path("config")  # Use real config
        return InboxWatcher(inbox_dir, config_dir)

    def test_init_creates_directories(self, inbox_dir: Path, watcher: InboxWatcher):
        """Test watcher creates required directories."""
        assert watcher.new_dir.exists()
        assert watcher.processing_dir.exists()
        assert watcher.done_dir.exists()
        assert watcher.failed_dir.exists()

    def test_scan_empty_inbox(self, watcher: InboxWatcher):
        """Test scanning empty inbox."""
        stats = watcher.scan()

        assert stats["processed"] == 0
        assert stats["failed"] == 0
        assert stats["skipped"] == 0

    def test_scan_processes_markdown_file(self, watcher: InboxWatcher):
        """Test scanning and processing markdown file."""
        # Create test file in new/
        test_file = watcher.new_dir / "test-doc.md"
        test_file.write_text(
            """---
title: Test Document
---

# Hello

Content here.
"""
        )

        # Scan inbox
        stats = watcher.scan()

        # File should be processed and moved to done/
        assert stats["processed"] == 1
        assert stats["failed"] == 0
        assert not test_file.exists()  # Moved from new/
        assert (watcher.done_dir / "test-doc.md").exists()

        # Check that normalized output was created
        queue_dir = Path("wiki_system/domains/general/queue")
        assert queue_dir.exists()
        assert len(list(queue_dir.glob("*.md"))) > 0

    def test_scan_processes_text_file(self, watcher: InboxWatcher):
        """Test scanning and processing text file."""
        test_file = watcher.new_dir / "notes.txt"
        test_file.write_text("My Notes\n\nContent here.")

        stats = watcher.scan()

        assert stats["processed"] == 1
        assert (watcher.done_dir / "notes.txt").exists()

    def test_scan_processes_multiple_files(self, watcher: InboxWatcher):
        """Test scanning and processing multiple files."""
        # Create multiple test files
        for i in range(3):
            test_file = watcher.new_dir / f"doc{i}.md"
            test_file.write_text(f"# Document {i}\n\nContent.")

        stats = watcher.scan()

        assert stats["processed"] == 3
        assert stats["failed"] == 0
        assert len(list(watcher.done_dir.glob("*.md"))) == 3
        assert len(list(watcher.new_dir.glob("*.md"))) == 0

    def test_scan_handles_unsupported_file(self, watcher: InboxWatcher):
        """Test handling unsupported file type."""
        # Create unsupported file type
        test_file = watcher.new_dir / "document.pdf"
        test_file.write_bytes(b"fake pdf content")

        stats = watcher.scan()

        # Should fail (no adapter for PDF)
        assert stats["processed"] == 0
        assert stats["failed"] == 1
        assert (watcher.failed_dir / "document.pdf").exists()

        # Should have error log
        error_log = watcher.failed_dir / "document.pdf.error"
        assert error_log.exists()
        error_text = error_log.read_text()
        assert "No adapter found" in error_text

    def test_process_file_moves_through_stages(self, watcher: InboxWatcher):
        """Test file moves through processing stages."""
        test_file = watcher.new_dir / "test.md"
        test_file.write_text("# Test\n\nContent.")

        # Initially in new/
        assert test_file.exists()
        assert not (watcher.processing_dir / "test.md").exists()
        assert not (watcher.done_dir / "test.md").exists()

        # Process
        watcher.scan()

        # Should be in done/ now
        assert not test_file.exists()
        assert not (watcher.processing_dir / "test.md").exists()
        assert (watcher.done_dir / "test.md").exists()

    def test_failed_file_collision_handling(self, watcher: InboxWatcher):
        """Test handling when failed file already exists."""
        # Create a file that will fail
        test_file = watcher.new_dir / "bad.pdf"
        test_file.write_bytes(b"content")

        # First failure
        watcher.scan()
        assert (watcher.failed_dir / "bad.pdf").exists()

        # Create another file with same name
        test_file2 = watcher.new_dir / "bad.pdf"
        test_file2.write_bytes(b"content2")

        # Second failure should append counter
        watcher.scan()
        assert (watcher.failed_dir / "bad_1.pdf").exists()

    def test_scan_ignores_directories(self, watcher: InboxWatcher):
        """Test scan ignores subdirectories."""
        # Create a subdirectory in new/
        subdir = watcher.new_dir / "subdir"
        subdir.mkdir()
        (subdir / "file.md").write_text("# Test\n\nContent.")

        stats = watcher.scan()

        # Should not process files in subdirectories
        assert stats["processed"] == 0
        assert subdir.exists()  # Subdirectory still there

    def test_processing_preserves_metadata(self, watcher: InboxWatcher):
        """Test processing preserves frontmatter metadata."""
        test_file = watcher.new_dir / "test.md"
        test_file.write_text(
            """---
title: My Title
author: John Doe
tags:
  - test
---

Content.
"""
        )

        watcher.scan()

        # Find output in queue
        queue_dir = Path("wiki_system/domains/general/queue")
        outputs = list(queue_dir.glob("*my-title*.md"))
        assert len(outputs) > 0

        output = outputs[0]
        content = output.read_text()

        # Metadata should be preserved
        assert "title: My Title" in content
        assert "author: John Doe" in content
        assert "tags:" in content

    def test_domain_routing_in_watcher(self, watcher: InboxWatcher):
        """Test domain routing works through watcher."""
        # Create file with path that should route to homelab
        test_file = watcher.new_dir / "proxmox-setup.md"
        test_file.write_text("# Proxmox Setup\n\nContent.")

        watcher.scan()

        # Should be routed to homelab domain
        homelab_queue = Path("wiki_system/domains/homelab/queue")
        outputs = list(homelab_queue.glob("*.md"))
        assert len(outputs) > 0

    def test_explicit_domain_routing(self, watcher: InboxWatcher):
        """Test explicit domain in frontmatter is respected."""
        test_file = watcher.new_dir / "test.md"
        test_file.write_text(
            """---
domain: personal
---

# Test

Content.
"""
        )

        watcher.scan()

        # Should be in personal domain queue
        personal_queue = Path("wiki_system/domains/personal/queue")
        outputs = list(personal_queue.glob("*.md"))
        assert len(outputs) > 0

    def test_error_on_processing_moves_back_to_new(
        self, watcher: InboxWatcher, monkeypatch: pytest.MonkeyPatch
    ):
        """Test file moves back to new/ if processing fails."""
        test_file = watcher.new_dir / "test.md"
        test_file.write_text("# Test\n\nContent.")

        # Mock pipeline.process_file to raise exception
        def mock_process_file(filepath):
            raise RuntimeError("Simulated processing error")

        monkeypatch.setattr(watcher.pipeline, "process_file", mock_process_file)

        # Scan should handle error
        stats = watcher.scan()

        assert stats["processed"] == 0
        assert stats["failed"] == 1

        # File should be in failed/ (moved from new after error)
        assert (watcher.failed_dir / "test.md").exists()
