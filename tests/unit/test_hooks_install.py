"""Idempotency and isolation tests for `llm-wiki hooks install/uninstall`.

Story 1.13 — AC: 1, 2, 3, 4
"""

import io
import json
import os
import sys
from pathlib import Path

from click.testing import CliRunner

from llm_wiki.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(tmp_path: Path) -> Path:
    return tmp_path / ".claude" / "settings.json"


def _all_commands(data: dict, event: str) -> list[str]:
    return [
        h["command"]
        for entry in data.get("hooks", {}).get(event, [])
        for h in entry.get("hooks", [])
    ]


# ---------------------------------------------------------------------------
# Install idempotency (AC: 4)
# ---------------------------------------------------------------------------


def test_install_idempotent(tmp_path: Path):
    """Second install must not create duplicate hook entries."""
    settings_path = _settings(tmp_path)
    settings_path.parent.mkdir()
    runner = CliRunner()

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(
            main,
            [
                "hooks",
                "install",
                "--scope",
                "project",
                "--wiki-base",
                str(tmp_path / "wiki_system"),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output

        result = runner.invoke(
            main,
            [
                "hooks",
                "install",
                "--scope",
                "project",
                "--wiki-base",
                str(tmp_path / "wiki_system"),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0, result.output
    finally:
        os.chdir(cwd)

    settings = json.loads(settings_path.read_text())
    for event in ("SessionEnd", "PreCompact"):
        cmds = _all_commands(settings, event)
        capture_cmds = [c for c in cmds if "capture_session.py" in c]
        assert len(capture_cmds) == 1, f"Expected 1 hook for {event}, got {len(capture_cmds)}"


def test_install_updates_wiki_base(tmp_path: Path):
    """Re-install with a different --wiki-base replaces the old entry, no duplicates."""
    settings_path = _settings(tmp_path)
    settings_path.parent.mkdir()
    runner = CliRunner()

    wiki_a = tmp_path / "wiki_a"
    wiki_b = tmp_path / "wiki_b"

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        runner.invoke(
            main,
            ["hooks", "install", "--scope", "project", "--wiki-base", str(wiki_a)],
            catch_exceptions=False,
        )
        runner.invoke(
            main,
            ["hooks", "install", "--scope", "project", "--wiki-base", str(wiki_b)],
            catch_exceptions=False,
        )
    finally:
        os.chdir(cwd)

    settings = json.loads(settings_path.read_text())
    for event in ("SessionEnd", "PreCompact"):
        cmds = _all_commands(settings, event)
        capture_cmds = [c for c in cmds if "capture_session.py" in c]
        assert len(capture_cmds) == 1, f"Expected 1 hook for {event} after wiki-base update"
        assert str(wiki_a) not in capture_cmds[0], "Old wiki-base should have been replaced"
        assert str(wiki_b) in capture_cmds[0], "New wiki-base should be present"


# ---------------------------------------------------------------------------
# Uninstall isolation (AC: 2)
# ---------------------------------------------------------------------------


def test_uninstall_preserves_other_hooks(tmp_path: Path):
    """Uninstall removes only llm-wiki entries; unrelated hooks survive."""
    settings_path = _settings(tmp_path)
    settings_path.parent.mkdir()
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionEnd": [{"hooks": [{"type": "command", "command": "echo other-hook"}]}]
                }
            }
        )
    )

    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        runner.invoke(
            main,
            [
                "hooks",
                "install",
                "--scope",
                "project",
                "--wiki-base",
                str(tmp_path / "wiki_system"),
            ],
        )
        runner.invoke(main, ["hooks", "uninstall", "--scope", "project"])
    finally:
        os.chdir(cwd)

    settings = json.loads(settings_path.read_text())
    commands = _all_commands(settings, "SessionEnd")
    assert any("other-hook" in c for c in commands), "Unrelated hook must survive uninstall"
    assert not any("capture_session" in c for c in commands), (
        "llm-wiki hook must be gone after uninstall"
    )


# ---------------------------------------------------------------------------
# capture_session.py — atomic write (AC: 3)
# ---------------------------------------------------------------------------


def test_capture_session_atomic_write(tmp_path: Path):
    """capture_session writes to a temp file then renames — no partial files."""
    from llm_wiki.hook_templates import capture_session

    inbox_dir = tmp_path / "wiki_system" / "inbox" / "new"
    inbox_dir.mkdir(parents=True)

    # Create a fake transcript file
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"role":"user","content":"hello"}\n')

    payload = {"transcript_path": str(transcript), "session_id": "test-session-id"}

    original_stdin = sys.stdin
    sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode()))
    original_argv = sys.argv
    sys.argv = ["capture_session.py", "SessionEnd", str(inbox_dir)]
    try:
        exit_code = capture_session.main()
    finally:
        sys.stdin = original_stdin
        sys.argv = original_argv

    assert exit_code == 0
    files = list(inbox_dir.iterdir())
    assert len(files) == 1, f"Expected 1 file in inbox, got {files}"
    assert files[0].suffix == ".jsonl"
    assert "session-" in files[0].name
    assert "SessionEnd" in files[0].name
    # No stray .tmp files
    assert not any(f.suffix == ".tmp" for f in inbox_dir.iterdir())
    # Content matches original
    assert files[0].read_text() == transcript.read_text()


# ---------------------------------------------------------------------------
# Dry-run (AC: 1)
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write(tmp_path: Path):
    """--dry-run prints JSON to stdout but must NOT create a settings file."""
    settings_path = _settings(tmp_path)
    settings_path.parent.mkdir()
    runner = CliRunner()

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(
            main,
            [
                "hooks",
                "install",
                "--scope",
                "project",
                "--wiki-base",
                str(tmp_path / "wiki_system"),
                "--dry-run",
            ],
            catch_exceptions=False,
        )
    finally:
        os.chdir(cwd)

    assert result.exit_code == 0, result.output
    assert not settings_path.exists(), "dry-run must not write settings file"
    parsed = json.loads(result.output)
    assert "hooks" in parsed, "dry-run output must be valid settings JSON"


# ---------------------------------------------------------------------------
# Hook JSON structure (AC: 1)
# ---------------------------------------------------------------------------


def test_hook_entry_structure(tmp_path: Path):
    """Installed hooks must have correct Claude Code JSON schema structure."""
    settings_path = _settings(tmp_path)
    settings_path.parent.mkdir()
    runner = CliRunner()

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        runner.invoke(
            main,
            [
                "hooks",
                "install",
                "--scope",
                "project",
                "--wiki-base",
                str(tmp_path / "wiki_system"),
            ],
            catch_exceptions=False,
        )
    finally:
        os.chdir(cwd)

    settings = json.loads(settings_path.read_text())
    for event in ("SessionEnd", "PreCompact"):
        entries = settings["hooks"][event]
        assert isinstance(entries, list) and len(entries) == 1
        entry = entries[0]
        assert "hooks" in entry, "entry must have 'hooks' key"
        hook = entry["hooks"][0]
        assert hook["type"] == "command", "hook type must be 'command'"
        assert "capture_session.py" in hook["command"], "command must reference capture_session.py"
        assert str(event) in hook["command"], f"command must reference hook event {event}"


# ---------------------------------------------------------------------------
# Uninstall — settings file absent (AC: 2)
# ---------------------------------------------------------------------------


def test_uninstall_no_settings_file(tmp_path: Path):
    """Uninstall when settings file is absent must exit cleanly."""
    settings_path = _settings(tmp_path)
    settings_path.parent.mkdir()
    runner = CliRunner()

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(main, ["hooks", "uninstall", "--scope", "project"])
    finally:
        os.chdir(cwd)

    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Uninstall removes PreCompact hooks (AC: 2)
# ---------------------------------------------------------------------------


def test_uninstall_removes_precompact_hooks(tmp_path: Path):
    """Uninstall must remove llm-wiki hooks from PreCompact, preserving unrelated ones."""
    settings_path = _settings(tmp_path)
    settings_path.parent.mkdir()
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreCompact": [
                        {"hooks": [{"type": "command", "command": "echo other-compact-hook"}]}
                    ]
                }
            }
        )
    )

    runner = CliRunner()
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        runner.invoke(
            main,
            [
                "hooks",
                "install",
                "--scope",
                "project",
                "--wiki-base",
                str(tmp_path / "wiki_system"),
            ],
        )
        runner.invoke(main, ["hooks", "uninstall", "--scope", "project"])
    finally:
        os.chdir(cwd)

    settings = json.loads(settings_path.read_text())
    commands = _all_commands(settings, "PreCompact")
    assert any("other-compact-hook" in c for c in commands), (
        "Unrelated PreCompact hook must survive"
    )
    assert not any("capture_session" in c for c in commands), (
        "llm-wiki PreCompact hook must be removed"
    )


# ---------------------------------------------------------------------------
# capture_session.py — error paths and filename format (AC: 3)
# ---------------------------------------------------------------------------


def _run_capture_session(argv_tail: list[str], stdin_text: str) -> int:
    """Invoke capture_session.main() with controlled argv and stdin."""
    from llm_wiki.hook_templates import capture_session

    original_stdin = sys.stdin
    original_argv = sys.argv
    sys.stdin = io.TextIOWrapper(io.BytesIO(stdin_text.encode()))
    sys.argv = ["capture_session.py"] + argv_tail
    try:
        return capture_session.main()
    finally:
        sys.stdin = original_stdin
        sys.argv = original_argv


def test_capture_session_no_transcript_path(tmp_path: Path):
    """Payload without transcript_path must exit 0 (nothing to capture)."""
    inbox_dir = tmp_path / "inbox" / "new"
    inbox_dir.mkdir(parents=True)
    payload = {"session_id": "s1"}
    code = _run_capture_session(["SessionEnd", str(inbox_dir)], json.dumps(payload))
    assert code == 0
    assert list(inbox_dir.iterdir()) == [], "No file should be written when transcript_path absent"


def test_capture_session_invalid_json_stdin(tmp_path: Path):
    """Invalid JSON on stdin must exit 1."""
    inbox_dir = tmp_path / "inbox" / "new"
    inbox_dir.mkdir(parents=True)
    code = _run_capture_session(["SessionEnd", str(inbox_dir)], "not-valid-json{{{")
    assert code == 1


def test_capture_session_missing_transcript_file(tmp_path: Path):
    """Non-existent transcript_path must exit 1."""
    inbox_dir = tmp_path / "inbox" / "new"
    inbox_dir.mkdir(parents=True)
    payload = {"transcript_path": str(tmp_path / "ghost.jsonl"), "session_id": "s1"}
    code = _run_capture_session(["SessionEnd", str(inbox_dir)], json.dumps(payload))
    assert code == 1


def test_capture_session_missing_args():
    """Invoking capture_session with no args must exit 2 (usage error)."""
    from llm_wiki.hook_templates import capture_session

    original_argv = sys.argv
    sys.argv = ["capture_session.py"]
    try:
        code = capture_session.main()
    finally:
        sys.argv = original_argv
    assert code == 2


def test_capture_session_precompact_event_in_filename(tmp_path: Path):
    """Filename must embed the hook_name so PreCompact events are distinguishable."""
    inbox_dir = tmp_path / "inbox" / "new"
    inbox_dir.mkdir(parents=True)

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text('{"role":"user","content":"compact"}\n')
    payload = {"transcript_path": str(transcript), "session_id": "compact-session"}

    code = _run_capture_session(["PreCompact", str(inbox_dir)], json.dumps(payload))

    assert code == 0
    files = list(inbox_dir.iterdir())
    assert len(files) == 1
    assert "PreCompact" in files[0].name, "Hook event name must appear in filename"
    assert "compact-session" in files[0].name, "Session ID must appear in filename"
