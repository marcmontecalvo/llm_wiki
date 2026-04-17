#!/usr/bin/env python3
"""Claude Code session capture hook.

Installed by ``llm-wiki hooks install`` and invoked by Claude Code for
``SessionEnd`` and ``PreCompact`` events. Reads the hook payload from stdin,
copies the transcript into the wiki inbox, and exits.

Usage (as invoked by Claude Code):
    capture_session.py <hook_name> <wiki_inbox_dir>

Stdin payload (JSON) contains at minimum::

    {"transcript_path": "/path/to/transcript.jsonl", "session_id": "..."}

We never touch the original transcript; we only copy it.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    """Entry point. Returns process exit code."""
    if len(sys.argv) < 3:
        print(
            "usage: capture_session.py <hook_name> <wiki_inbox_dir>",
            file=sys.stderr,
        )
        return 2

    hook_name = sys.argv[1]
    inbox_dir = Path(sys.argv[2])

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"capture_session: invalid JSON on stdin: {e}", file=sys.stderr)
        return 1

    transcript_path_raw = payload.get("transcript_path")
    if not transcript_path_raw:
        # Nothing to capture — not an error; some hook events may lack a transcript.
        return 0

    transcript_path = Path(transcript_path_raw)
    if not transcript_path.exists():
        print(
            f"capture_session: transcript not found: {transcript_path}",
            file=sys.stderr,
        )
        return 1

    inbox_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(payload.get("session_id", "")).strip() or "unknown"
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = transcript_path.suffix or ".jsonl"
    # Filename matches ClaudeSessionAdapter.SESSION_PREFIX
    dest = inbox_dir / f"session-{ts}-{session_id}-{hook_name}{suffix}"

    shutil.copy2(transcript_path, dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
