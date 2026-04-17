# ADR 004: Single Capture Script for Claude Code Hooks

## Status

Accepted.

## Context

The port plan for adopting ideas from `claude-memory-compiler` proposed
shipping two hook scripts:

- `templates/hooks/session_end.py` (SessionEnd event)
- `templates/hooks/pre_compact.py` (PreCompact event)

## Decision

We ship **one** parameterized script instead:

- `src/llm_wiki/hook_templates/capture_session.py`

The installed hook command passes the event name and the inbox path as
positional arguments:

```
"<python>" "<...>/capture_session.py" SessionEnd "<wiki>/inbox/new"
"<python>" "<...>/capture_session.py" PreCompact "<wiki>/inbox/new"
```

The script reads the Claude Code hook payload from stdin, derives a
filename of the form `session-<ts>-<session_id>-<hook_name>.<ext>`, and
copies the transcript into the inbox.

## Rationale

- Both events do the same work: persist the transcript file into the inbox.
  Splitting them into two scripts would duplicate ~60 lines with a single
  string differing.
- One code path means one place to fix bugs, one place to audit, and one
  packaged resource to resolve via `importlib.resources`.
- The hook name is still preserved in the filename, so downstream adapters
  (`ClaudeSessionAdapter`) can tag pages with `capture_hook=SessionEnd` or
  `capture_hook=PreCompact` without losing provenance.

## Consequences

- `llm-wiki hooks install` writes the same command pattern for both events,
  varying only the hook-name argument.
- Packaging changes: the script lives under the package at
  `llm_wiki/hook_templates/` rather than the top-level `templates/hooks/`
  directory, so wheel installs work without needing extra `package-data`
  wiring.
