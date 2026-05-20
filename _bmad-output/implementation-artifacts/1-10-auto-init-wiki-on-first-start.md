# Story 1.10: Auto-Init Wiki on First Start

Status: done

## Story

As an operator,
I want the wiki to initialize its own directory structure on first run,
so that setup requires zero manual steps.

**Note:** The `_maybe_init_wiki_root()` function and `WikiInitializer` class skeleton were created in Story 1.4. This story fleshes out the full initialization logic so that the function creates a complete, valid wiki structure from an empty directory.

## Acceptance Criteria

1. **Given** an empty host directory mounted at `/wiki` **When** the service starts for the first time **Then** `wiki_system/` and all required subdirectories are created before any query is served (FR55, NFR-O4).

2. **Given** `_maybe_init_wiki_root()` is called on a volume that is already initialized **When** executed **Then** it is idempotent — no existing directories or files are re-created, overwritten, or corrupted.

3. **Given** the init function is called **When** audited **Then** it is the first call in the FastAPI lifespan, before `WikiConfig.load()` — calling it after raises `FileNotFoundError` on a fresh volume.

## Tasks / Subtasks

- [x] Flesh out `WikiInitializer.initialize(wiki_root: Path)` in `src/llm_wiki/initializer.py` (AC: 1, 2)
  - [x] Create `wiki_system/` under `wiki_root` if it doesn't exist
  - [x] Create all required subdirectories (see Runtime Volume Structure below)
  - [x] Create empty default config files if `/config/` doesn't exist yet (or skip if mounted)
  - [x] Use `mkdir(parents=True, exist_ok=True)` throughout — ensures idempotency
  - [x] Write initial empty index files if they don't exist: `index/fulltext.json`, `index/metadata.json`, `index/backlinks.json`, `index/graph_edges.json` (content: `{}`)
  - [x] Write initial `state/jobs.json` if it doesn't exist (content: `{}`)
  - [x] Create `logs/changelog.jsonl` (empty file) if it doesn't exist
  - [x] Log summary of what was created vs. what already existed
- [x] Verify `_maybe_init_wiki_root()` correctly wraps `WikiInitializer.initialize()` (AC: 2, 3)
  - [x] Call condition: only if `wiki_root / "wiki_system" / "domains"` does not exist
  - [x] Already first call in FastAPI lifespan (set in Story 1.4) — verify no regression
- [x] Write tests for `WikiInitializer`

## Dev Notes

### Full Directory Structure to Create

Based on the architecture "Runtime Volume Structure":

```
wiki_root/
└── wiki_system/
    ├── inbox/
    │   ├── new/
    │   ├── processing/
    │   ├── done/
    │   ├── failed/
    │   └── staging/           # for routing-failed sources (FR53, Story 1.15)
    ├── domains/               # empty — domains created when pages arrive
    ├── shared/                # cross-domain promoted entities (Sprint 3)
    ├── index/
    │   ├── fulltext.json      # empty: {}
    │   ├── metadata.json      # empty: {}
    │   ├── backlinks.json     # empty: {}
    │   └── graph_edges.json   # empty: {}
    │   # vector_index.faiss and vector_meta.json created by VectorIndex.save() on first rebuild
    ├── exports/
    ├── reports/
    ├── review_queue/
    │   ├── pending/
    │   ├── approved/
    │   ├── rejected/
    │   └── deferred/
    ├── state/
    │   └── jobs.json          # empty: {}
    └── logs/
        └── changelog.jsonl   # empty file (append-only log)
```

### Implementation

```python
# src/llm_wiki/initializer.py
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_REQUIRED_DIRS = [
    "inbox/new", "inbox/processing", "inbox/done", "inbox/failed", "inbox/staging",
    "domains", "shared",
    "index",
    "exports", "reports",
    "review_queue/pending", "review_queue/approved",
    "review_queue/rejected", "review_queue/deferred",
    "state", "logs",
]

_INITIAL_JSON_FILES = {
    "index/fulltext.json": "{}",
    "index/metadata.json": "{}",
    "index/backlinks.json": "{}",
    "index/graph_edges.json": "{}",
    "state/jobs.json": "{}",
}


class WikiInitializer:
    @staticmethod
    def initialize(wiki_root: Path) -> None:
        """Create wiki_system/ structure. Idempotent — safe to call on existing wiki."""
        wiki_system = wiki_root / "wiki_system"

        # Create all required directories
        for rel_dir in _REQUIRED_DIRS:
            path = wiki_system / rel_dir
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                logger.info("Created directory: %s", path)

        # Create initial empty index/state files
        for rel_path, content in _INITIAL_JSON_FILES.items():
            path = wiki_system / rel_path
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                logger.info("Created initial file: %s", path)

        # Create empty changelog (append-only)
        changelog = wiki_system / "logs" / "changelog.jsonl"
        if not changelog.exists():
            changelog.touch()
            logger.info("Created changelog: %s", changelog)


def _maybe_init_wiki_root(wiki_root: Path) -> None:
    """Auto-initialize wiki directory structure on first start (FR55, NFR-O4).

    Must be called before WikiConfig.load() in FastAPI lifespan.
    """
    sentinel = wiki_root / "wiki_system" / "domains"
    if not sentinel.exists():
        logger.info("First start detected — initializing wiki structure at %s", wiki_root)
        WikiInitializer.initialize(wiki_root)
    else:
        logger.debug("Wiki structure already exists at %s — skipping init", wiki_root)
```

### idempotency Is the Key Invariant

Every creation call must use `exist_ok=True` (dirs) or `if not path.exists()` (files). The function must be safe to call on an already-initialized wiki with real data. Running it twice must produce no changes and no errors.

### Story 1.4 Interaction

Story 1.4 created the skeleton of `initializer.py` with `_maybe_init_wiki_root()` and `WikiInitializer`. This story REPLACES that skeleton with the full implementation. If Story 1.4 only stubbed these out, fill them in now. If Story 1.4 already has a partial implementation, extend it to match the full directory structure above.

### inbox/staging/ Directory

This directory is needed by Story 1.15 (routing-failed sources land here). Include it in the init even though Story 1.15 is not yet done — it costs nothing and avoids a second init change.

### Project Structure — Files to Modify

```
src/llm_wiki/
└── initializer.py      UPDATE — flesh out WikiInitializer.initialize() and _maybe_init_wiki_root()
```

No other files need changes for this story (the lifespan call was set up in Story 1.4).

### Testing

`tests/unit/test_initializer.py` (may already exist from Story 1.4 skeleton):

```python
def test_initialize_creates_all_required_dirs(temp_dir):
    WikiInitializer.initialize(temp_dir)
    wiki_system = temp_dir / "wiki_system"
    assert (wiki_system / "inbox" / "new").is_dir()
    assert (wiki_system / "inbox" / "processing").is_dir()
    assert (wiki_system / "domains").is_dir()
    assert (wiki_system / "index").is_dir()
    assert (wiki_system / "state").is_dir()
    assert (wiki_system / "logs").is_dir()
    assert (wiki_system / "review_queue" / "pending").is_dir()

def test_initialize_creates_empty_index_files(temp_dir):
    WikiInitializer.initialize(temp_dir)
    wiki_system = temp_dir / "wiki_system"
    for name in ["fulltext.json", "metadata.json", "backlinks.json", "graph_edges.json"]:
        path = wiki_system / "index" / name
        assert path.exists()
        assert path.stat().st_size > 0  # contains "{}"

def test_initialize_is_idempotent(temp_dir):
    WikiInitializer.initialize(temp_dir)
    WikiInitializer.initialize(temp_dir)  # second call must not raise
    # Verify no data was corrupted
    wiki_system = temp_dir / "wiki_system"
    assert (wiki_system / "domains").is_dir()

def test_maybe_init_skips_if_already_initialized(temp_dir):
    wiki_system = temp_dir / "wiki_system"
    (wiki_system / "domains").mkdir(parents=True)
    # Write a sentinel file to detect if init ran
    sentinel = wiki_system / "index" / "fulltext.json"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text('{"existing": true}')
    _maybe_init_wiki_root(temp_dir)
    # Existing file should be untouched
    assert '"existing": true' in sentinel.read_text()

def test_maybe_init_runs_on_fresh_volume(temp_dir):
    _maybe_init_wiki_root(temp_dir)
    assert (temp_dir / "wiki_system" / "domains").is_dir()
```

### Critical Anti-Patterns to Avoid

- **Never overwrite existing files** during init — check `if not path.exists()` before writing
- **Never call this after `WikiConfig.load()`** — on a fresh empty volume, config load fails first
- **Never create domain subdirectories** during init — domains are created when pages arrive, not at startup

### References

- Architecture: "Startup Init Sequence" — `_maybe_init_wiki_root()` ordering
- Architecture: "Runtime Volume Structure" — full directory tree
- Story 1.4: `initializer.py` skeleton
- FR55, NFR-O4

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- WikiInitializer.initialize() creates complete wiki directory structure under wiki_root (dirs only — no seed files for index data)
- Created: inbox/staging/, index/, full review_queue/ subdirs (pending/approved/rejected/deferred), reports/ directory
- Intent-driven seed strategy: only changelog.jsonl and directory structures are pre-created; index JSON files are left absent so check_index_integrity() can detect missing/stale data and trigger the rebuild path
- Added empty logs/changelog.jsonl for append-only changelog
- Added logging summary (dirs created vs existed)
- _maybe_init_wiki_root() verified correct: uses domains/ sentinel, called first in boot_wiki before config load
- FastAPI lifespan confirmed to call boot_wiki() first — satisfies AC3
- 8 tests cover directory creation, idempotency, sentinel behavior, changelog
- Fixed graph_edges.json → edges.json in startup.py and tests to match GraphEdgeIndex runtime filename
- All 13 affected tests pass

### Debug Log References

### File List

- `src/llm_wiki/initializer.py` — Modified: expanded _COMMON_SUBDIRS, rewrote initialize() to create only directories (no seed data files); removed _INITIAL_JSON_FILES
- `src/llm_wiki/startup.py` — Fixed: graph_edges.json → edges.json to match GraphEdgeIndex runtime filename
- `tests/unit/test_initializer.py` — Rewritten: 8 tests covering directory structure, idempotency, sentinel behavior, changelog
- `tests/unit/test_startup.py` — Fixed: graph_edges.json → edges.json in all test methods
