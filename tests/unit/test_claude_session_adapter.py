"""Tests for ClaudeSessionAdapter."""

import json
from pathlib import Path

from llm_wiki.adapters.claude_session import ClaudeSessionAdapter


class TestClaudeSessionAdapterCanParse:
    """Tests for can_parse filename matching."""

    def test_accepts_session_jsonl(self):
        """Accepts session-*.jsonl filenames."""
        assert ClaudeSessionAdapter.can_parse(Path("session-20260416T100000Z-abc.jsonl"))

    def test_accepts_session_json(self):
        """Accepts session-*.json filenames."""
        assert ClaudeSessionAdapter.can_parse(Path("session-abc.json"))

    def test_rejects_plain_jsonl_without_prefix(self):
        """Rejects .jsonl files that don't have the session- prefix."""
        assert not ClaudeSessionAdapter.can_parse(Path("data.jsonl"))

    def test_rejects_non_json_suffix(self):
        """Rejects non-json/jsonl files even with session- prefix."""
        assert not ClaudeSessionAdapter.can_parse(Path("session-foo.md"))


class TestClaudeSessionAdapterExtractMetadata:
    """Tests for metadata extraction."""

    def test_metadata_has_expected_fields(self, temp_dir: Path):
        """Metadata carries source_type, adapter, and ingested_at."""
        filepath = temp_dir / "session-20260416-abc.jsonl"
        line = json.dumps(
            {
                "role": "user",
                "content": "hello",
                "session_id": "abc-123",
                "_capture_hook": "SessionEnd",
            }
        )
        filepath.write_text(line + "\n", encoding="utf-8")

        adapter = ClaudeSessionAdapter()
        metadata = adapter.extract_metadata(filepath, filepath.read_text(encoding="utf-8"))

        assert metadata["source_type"] == "claude-session"
        assert metadata["adapter"] == "claude-session"
        assert metadata["session_id"] == "abc-123"
        assert metadata["capture_hook"] == "SessionEnd"
        assert metadata["message_count"] == 1
        assert "claude-session" in metadata["tags"]

    def test_handles_jsonl_with_blank_lines(self, temp_dir: Path):
        """Blank lines are ignored."""
        filepath = temp_dir / "session-x.jsonl"
        content = "\n".join(
            [
                json.dumps({"role": "user", "content": "hi"}),
                "",
                json.dumps({"role": "assistant", "content": "hello"}),
                "",
            ]
        )
        filepath.write_text(content, encoding="utf-8")

        adapter = ClaudeSessionAdapter()
        metadata = adapter.extract_metadata(filepath, content)
        assert metadata["message_count"] == 2

    def test_json_array_format(self, temp_dir: Path):
        """Single-JSON array format is supported."""
        filepath = temp_dir / "session-arr.json"
        payload = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]
        filepath.write_text(json.dumps(payload), encoding="utf-8")

        adapter = ClaudeSessionAdapter()
        metadata = adapter.extract_metadata(filepath, filepath.read_text(encoding="utf-8"))
        assert metadata["message_count"] == 2


class TestClaudeSessionAdapterNormalize:
    """Tests for markdown normalization."""

    def test_renders_sections_per_message(self, temp_dir: Path):
        """Each message becomes a numbered ## section."""
        filepath = temp_dir / "session-foo.jsonl"
        content = "\n".join(
            [
                json.dumps({"role": "user", "content": "What is Python?"}),
                json.dumps({"role": "assistant", "content": "A programming language."}),
            ]
        )
        filepath.write_text(content, encoding="utf-8")

        adapter = ClaudeSessionAdapter()
        md = adapter.normalize_to_markdown(filepath, content)

        assert "## 1. User" in md
        assert "## 2. Assistant" in md
        assert "What is Python?" in md
        assert "A programming language." in md

    def test_content_block_text_extracted(self, temp_dir: Path):
        """Content block arrays with type=text surface properly."""
        filepath = temp_dir / "session-bar.jsonl"
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Here is the fix."},
                {"type": "tool_use", "name": "Edit"},
                {"type": "text", "text": "Done."},
            ],
        }
        content = json.dumps(msg)
        filepath.write_text(content, encoding="utf-8")

        adapter = ClaudeSessionAdapter()
        md = adapter.normalize_to_markdown(filepath, content)

        assert "Here is the fix." in md
        assert "Done." in md
        assert "[tool use: Edit]" in md

    def test_empty_transcript_returns_placeholder(self, temp_dir: Path):
        """Empty transcripts produce a non-empty placeholder string."""
        filepath = temp_dir / "session-empty.jsonl"
        filepath.write_text("", encoding="utf-8")

        adapter = ClaudeSessionAdapter()
        md = adapter.normalize_to_markdown(filepath, "")
        assert md  # non-empty placeholder
        assert "Empty" in md or "no text" in md.lower()

    def test_process_end_to_end(self, temp_dir: Path):
        """process() returns (metadata, markdown) together."""
        filepath = temp_dir / "session-e2e.jsonl"
        content = json.dumps({"role": "user", "content": "hi"})
        filepath.write_text(content, encoding="utf-8")

        adapter = ClaudeSessionAdapter()
        metadata, markdown = adapter.process(filepath)

        assert metadata["source_type"] == "claude-session"
        assert "## 1. User" in markdown
