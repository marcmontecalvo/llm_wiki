# Story 1.13: Claude Code Hooks

Status: ready-for-dev

## Story

As a Claude Code user,
I want session capture hooks that automatically feed Claude sessions into the wiki,
So that the wiki stays current without manual ingest steps.

**Note:** The hook install/uninstall commands and the `capture_session.py` hook script are already implemented. This story verifies they work correctly in the Docker context and ensures the idempotency invariant is solid. Read `src/llm_wiki/cli.py:2853-3030` and `src/llm_wiki/hook_templates/capture_session.py` before implementing — most of the work already exists.

## Acceptance Criteria

1. **Given** `llm-wiki hooks install` is run **When** executed **Then** Claude Code `SessionEnd` and `PreCompact` hooks are installed that capture transcripts to `inbox/new/`.

2. **Given** `llm-wiki hooks uninstall` is run **When** executed **Then** the hooks are removed cleanly without affecting any other Claude Code configuration.

3. **Given** the hooks are installed and a Claude Code session ends **When** the `SessionEnd` hook fires **Then** the transcript is written to `inbox/new/` as a JSONL file and the daemon ingests it on the next scan cycle (FR33).

4. **Given** `llm-wiki hooks install` is run when hooks are already installed **When** executed **Then** it is idempotent — no duplicate hooks are created.

## Tasks / Subtasks

- [ ] Verify existing hook install/uninstall commands work correctly (AC: 1, 2, 4)
  - [ ] Read `src/llm_wiki/cli.py:2853-3030` — `hooks_install` and `hooks_uninstall` commands
  - [ ] Verify idempotency logic: second `install` does NOT create duplicate hook entries
  - [ ] Verify `uninstall` removes only llm-wiki hooks, leaves other hooks intact
  - [ ] Fix any bugs found (edge cases: empty hooks block, missing events, malformed JSON)
- [ ] Verify `capture_session.py` hook script works correctly (AC: 3)
  - [ ] Read `src/llm_wiki/hook_templates/capture_session.py` — understand current behavior
  - [ ] Verify it reads JSON from stdin correctly for both `SessionEnd` and `PreCompact` events
  - [ ] Verify it writes to `inbox/new/` with correct filename pattern
  - [ ] Verify `wiki_base` is resolved correctly from the hook command path in Docker context
- [ ] Verify Docker compatibility (AC: 1, 3)
  - [ ] The hook script runs in the host Claude Code process, not inside Docker
  - [ ] `inbox/new/` must be accessible from the host; verify `wiki_base` path resolution
  - [ ] Document in dev notes how the hook→inbox→daemon handoff works across host/container boundary
- [ ] Write integration test for idempotency (AC: 4)
  - [ ] `tests/unit/test_hooks_install.py` — test install twice, verify no duplicate entries
  - [ ] Test uninstall clears only llm-wiki entries from the hooks block
  - [ ] Test install when hooks block contains unrelated entries — those must be preserved

## Dev Notes

### Existing Implementation — Read Before Touching

The hooks feature is already substantially implemented:

**CLI commands** in `src/llm_wiki/cli.py:2853-3030`:
- `hooks install --scope [user|project] --wiki-base <path> --dry-run`
- `hooks uninstall --scope [user|project]`

**Hook script**: `src/llm_wiki/hook_templates/capture_session.py`
- Installed via `importlib.resources` — packaged inside `llm_wiki.hook_templates`
- Receives JSON event data on stdin
- Writes JSONL to `inbox/new/session-{ts}-{session_id}-{hook_name}.jsonl`

**Settings target** (`--scope project`): `.claude/settings.json`
**Settings target** (`--scope user`): `~/.claude/settings.json`

### Idempotency Pattern in hooks_install()

The existing code uses a filter pattern to prevent duplicate entries:

```python
existing = hooks_block.get(event)
# ... deduplicate by checking if command already present ...
for h in item.get("hooks", [])
    if capture_script_str not in h.get("command", "")
```

Verify this deduplication is correct — it should be keyed on the capture_script path, not the full command string (which includes `--wiki-base` that may differ between calls).

**Potential bug to check**: If the user runs `hooks install --wiki-base /path/A` then `hooks install --wiki-base /path/B`, does the second call correctly update the wiki-base rather than leaving the old entry? The correct behavior: replace the existing llm-wiki hook entry with the new one (same script path, different wiki-base argument).

### Docker Context — Host/Container Boundary

The hooks run on the **host machine** inside the Claude Code process. The wiki container runs separately. This means:

- `inbox/new/` must be a path accessible on the **host** filesystem
- If using a Docker volume (e.g., `~/my-wiki/wiki_system`), the `--wiki-base` passed to `hooks install` must be the **host-side** path of the volume mount
- Inside the container, the wiki sees the same directory via `/wiki/wiki_system`

This is not a code bug — it's an operational constraint. Document it in the install command's help text or error output.

```
# Example correct invocation for Docker setup:
llm-wiki hooks install --scope user --wiki-base ~/my-wiki/wiki_system
```

### Hook Settings JSON Structure

Claude Code `settings.json` format for hooks:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/capture_session.py --wiki-base /path/to/wiki_system"
          }
        ]
      }
    ],
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/capture_session.py --wiki-base /path/to/wiki_system"
          }
        ]
      }
    ]
  }
}
```

`--wiki-base` receives the wiki root (`wiki_system/`), consistent with every other component. `capture_session.py` derives `inbox/new/` internally: `inbox_dir = Path(args.wiki_base) / "inbox" / "new"`.

### capture_session.py Expected Behavior

```python
# Reads JSON from stdin (Claude Code hook event payload)
# Extracts: session_id, hook_event_name, transcript/messages
# Derives inbox path: wiki_base / "inbox" / "new"  (NOT passed directly as --wiki-base)
# Writes to: inbox_dir / f"session-{timestamp}-{session_id}-{hook_event_name}.jsonl"
# Exit 0 on success — Claude Code ignores non-zero exit from hooks
```

The file must be written atomically (write to temp then rename) to avoid the daemon picking up a partial file during a long write.

### Project Structure — Files to Verify/Modify

```
src/llm_wiki/
├── cli.py                              VERIFY — hooks install/uninstall idempotency (lines 2853-3030)
└── hook_templates/
    └── capture_session.py             VERIFY — atomic write, correct inbox path

tests/unit/
└── test_hooks_install.py              NEW — idempotency and isolation tests
```

### Testing

`tests/unit/test_hooks_install.py`:

```python
import json
from pathlib import Path
from click.testing import CliRunner
from llm_wiki.cli import main

def test_install_idempotent(tmp_path):
    """Second install must not create duplicate hook entries."""
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    runner = CliRunner()

    # First install
    result = runner.invoke(main, [
        "hooks", "install",
        "--scope", "project",
        "--wiki-base", str(tmp_path / "wiki_system"),
    ], catch_exceptions=False)
    assert result.exit_code == 0

    # Second install — must not duplicate
    result = runner.invoke(main, [
        "hooks", "install",
        "--scope", "project",
        "--wiki-base", str(tmp_path / "wiki_system"),
    ], catch_exceptions=False)
    assert result.exit_code == 0

    settings = json.loads(settings_path.read_text())
    hooks = settings["hooks"]
    for event in ("SessionEnd", "PreCompact"):
        all_commands = [
            h["command"]
            for entry in hooks.get(event, [])
            for h in entry.get("hooks", [])
        ]
        assert len(all_commands) == 1, f"Expected 1 hook for {event}, got {len(all_commands)}"

def test_uninstall_preserves_other_hooks(tmp_path):
    """Uninstall removes only llm-wiki entries, preserves others."""
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    # Pre-populate with unrelated hook
    existing = {
        "hooks": {
            "SessionEnd": [
                {"hooks": [{"type": "command", "command": "echo other-hook"}]}
            ]
        }
    }
    settings_path.write_text(json.dumps(existing))

    runner = CliRunner()
    runner.invoke(main, [
        "hooks", "install", "--scope", "project",
        "--wiki-base", str(tmp_path / "wiki_system"),
    ])
    runner.invoke(main, ["hooks", "uninstall", "--scope", "project"])

    settings = json.loads(settings_path.read_text())
    commands = [
        h["command"]
        for entry in settings.get("hooks", {}).get("SessionEnd", [])
        for h in entry.get("hooks", [])
    ]
    # Other hook must still be present
    assert any("other-hook" in c for c in commands)
    # llm-wiki hook must be gone
    assert not any("capture_session" in c for c in commands)
```

### Critical Anti-Patterns to Avoid

- **Never overwrite the entire hooks block** — merge with existing hooks; unrelated hooks must survive install/uninstall
- **Never hardcode the capture_session.py path** — use `importlib.resources` to locate it; works in both editable and wheel installs
- **Never write to inbox from inside the container** — hooks run on the host; the inbox path is a host-side path

### References

- Architecture: "Claude Code Hook Integration" — capture_session.py and hook events
- `src/llm_wiki/cli.py:2853-3030` — existing hooks install/uninstall commands
- `src/llm_wiki/hook_templates/capture_session.py` — hook script
- FR33: Session capture → wiki inbox pipeline

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
