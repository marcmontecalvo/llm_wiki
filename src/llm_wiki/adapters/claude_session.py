"""Claude Code session transcript adapter.

Normalizes Claude Code session transcripts (JSONL) into markdown suitable for
ingestion into the wiki. Session transcripts are captured automatically via
``SessionEnd`` and ``PreCompact`` hooks. See ``templates/hooks/`` for the hook
scripts and ``llm-wiki hooks install`` for installation.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.adapters.base import SourceAdapter


class ClaudeSessionAdapter(SourceAdapter):
    """Adapter for Claude Code session transcript files.

    Accepts ``.jsonl`` (one JSON object per line, Claude Code's native transcript
    format) and ``.json`` (a single JSON array of messages). Each message is
    rendered as a markdown section tagged by role.
    """

    # Filename prefix used by the shipped hooks. We avoid matching every .jsonl
    # on disk — only files the hooks created.
    SESSION_PREFIX = "session-"

    @classmethod
    def can_parse(cls, filepath: Path) -> bool:
        """Return True for Claude session transcript files.

        Matches ``session-*.jsonl`` and ``session-*.json`` to avoid colliding
        with unrelated JSON/JSONL files.
        """
        if filepath.suffix.lower() not in {".jsonl", ".json"}:
            return False
        return filepath.name.startswith(cls.SESSION_PREFIX)

    def _load_messages(self, filepath: Path, content: str) -> list[dict[str, Any]]:
        """Parse messages from transcript content.

        Args:
            filepath: Path to the transcript file (used to choose parser).
            content: Raw file content.

        Returns:
            List of message dicts. Returns empty list on unparseable content.
        """
        messages: list[dict[str, Any]] = []

        if filepath.suffix.lower() == ".jsonl":
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    messages.append(obj)
            return messages

        # .json — expect an array or an object with "messages" key
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []

        if isinstance(data, list):
            return [m for m in data if isinstance(m, dict)]
        if isinstance(data, dict):
            raw = data.get("messages", [])
            if isinstance(raw, list):
                return [m for m in raw if isinstance(m, dict)]
        return []

    def _message_text(self, message: dict[str, Any]) -> str:
        """Extract readable text from a transcript message.

        Claude Code transcripts use nested content blocks (text, tool_use,
        tool_result). We only surface text blocks; tool activity is summarized.
        """
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if not isinstance(content, list):
            return ""

        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            elif block_type == "tool_use":
                name = block.get("name", "tool")
                parts.append(f"_[tool use: {name}]_")
            elif block_type == "tool_result":
                parts.append("_[tool result]_")
        return "\n\n".join(parts).strip()

    def extract_metadata(self, filepath: Path, content: str) -> dict[str, Any]:
        """Extract metadata from a Claude session transcript.

        Args:
            filepath: Path to the transcript.
            content: File content.

        Returns:
            Metadata dict. Session id, message counts, and capture hook are
            pulled from the first message if present.
        """
        messages = self._load_messages(filepath, content)

        session_id = ""
        capture_hook = "unknown"
        for message in messages:
            if not session_id:
                sid = message.get("session_id") or message.get("sessionId")
                if isinstance(sid, str):
                    session_id = sid
            hook = message.get("_capture_hook")
            if isinstance(hook, str):
                capture_hook = hook

        # Derive title: prefer stem, fall back to session id
        stem = filepath.stem
        title = stem.replace("-", " ").replace("_", " ").title()

        metadata: dict[str, Any] = {
            "source_type": "claude-session",
            "source_path": str(filepath),
            "adapter": "claude-session",
            "title": title,
            "ingested_at": datetime.now(UTC),
            "message_count": len(messages),
            "capture_hook": capture_hook,
        }
        if session_id:
            metadata["session_id"] = session_id
            metadata["tags"] = ["claude-session", capture_hook]
        else:
            metadata["tags"] = ["claude-session", capture_hook]

        return metadata

    def normalize_to_markdown(self, filepath: Path, content: str) -> str:
        """Convert a transcript into readable markdown.

        Args:
            filepath: Path to the transcript.
            content: File content.

        Returns:
            Markdown with one ``##`` section per message.
        """
        messages = self._load_messages(filepath, content)
        if not messages:
            return "_Empty or unparseable session transcript._"

        sections: list[str] = []
        for i, message in enumerate(messages, start=1):
            role = str(message.get("role", "unknown")).strip() or "unknown"
            text = self._message_text(message)
            if not text:
                continue
            sections.append(f"## {i}. {role.title()}\n\n{text}")

        if not sections:
            return "_Session transcript had no text content._"

        return "\n\n".join(sections)
