# Story 1.2: Inbox Recovery and Index Integrity on Startup

Status: ready-for-dev

## Story

As a wiki operator,
I want the daemon to automatically recover from crashes and verify index integrity on every startup,
so that the service resumes without data loss or silent corruption after any restart.

## Acceptance Criteria

1. **Given** files exist in `inbox/processing/` when the daemon starts **When** the daemon initializes **Then** all files in `processing/` are moved back to `inbox/new/` for reprocessing before the scheduler starts. A warning is logged for each recovered file indicating it was found in an inconsistent state.

2. **Given** the daemon starts (clean or after crash) **When** it initializes **Then** it runs an index integrity check before beginning to serve queries or process inbox items. The integrity check verifies each expected index file exists and is non-empty (not a full parse — just existence and size check).

3. **Given** the integrity check detects a missing or zero-byte index file **When** this occurs **Then** the daemon triggers a full `IndexRebuildJob` synchronously before accepting any work. The rebuild completes within 60s for a wiki of up to 1,000 pages (NFR-P5).

4. **Given** a clean startup with no corruption and no orphaned inbox files **When** the daemon starts **Then** no rebuild is triggered and the daemon is fully operational within 60s (NFR-R1).

5. **Given** the daemon restarts after a crash mid-ingest **When** inbox recovery runs **Then** no file is permanently lost — all pre-crash inbox submissions are in `inbox/new/` and will be processed on the next scan cycle (NFR-R3).

## Tasks / Subtasks

- [ ] Add `recover_processing_dir()` to `InboxWatcher` (AC: 1, 5)
  - [ ] Scan `inbox/processing/` for all files
  - [ ] Move each file back to `inbox/new/` using `shutil.move()`
  - [ ] Log `WARNING` for each recovered file: `"Recovered orphaned file from processing/: {name}"`
  - [ ] Return count of recovered files
- [ ] Add index integrity check utility (AC: 2, 3, 4)
  - [ ] Create `src/llm_wiki/startup.py` with `IndexIntegrityCheck` class
  - [ ] `check(wiki_base: Path) -> list[str]`: returns list of missing/corrupt index file names
  - [ ] Check these 4 files: `index/fulltext.json`, `index/metadata.json`, `index/backlinks.json`, `index/graph_edges.json`
  - [ ] For vector index: check `index/vector_index.faiss` and `index/vector_meta.json` only if `features.vector_search: true`
  - [ ] An index file "passes" if it exists AND `file.stat().st_size > 0`
- [ ] Wire recovery and integrity check into `WikiDaemon.start()` (AC: 1, 2, 3, 4)
  - [ ] Call `InboxWatcher(inbox_dir=wiki_base/"inbox").recover_processing_dir()` before `scheduler.start()`
  - [ ] Call `IndexIntegrityCheck().check(wiki_base)` before `scheduler.start()`
  - [ ] If any corrupt/missing indexes found: run `IndexRebuildJob(wiki_base=wiki_base).execute()` synchronously
  - [ ] Log result of synchronous rebuild; if rebuild fails, log error but continue starting (don't crash)
- [ ] Write tests (see Testing section)

## Dev Notes

### Current State — What Needs to Change

**`src/llm_wiki/ingest/watcher.py`** — `InboxWatcher._process_file()` (line 116) moves files back to `new/` on exception during active processing, but there is NO startup recovery for files that got stuck in `processing/` due to a daemon crash mid-operation. The `recover_processing_dir()` method needs to be added.

**`src/llm_wiki/daemon/main.py`** — `WikiDaemon.start()` registers jobs and starts the scheduler but does NO startup checks before the scheduler begins. Recovery and integrity check must run before `self.scheduler.start()` (line 197).

**`wiki_base` in `main.py`** — Currently hardcoded as `Path("wiki_system")` at line 80. The recovery call should use this same reference.

### Inbox Recovery Implementation

```python
# src/llm_wiki/ingest/watcher.py — add to InboxWatcher class
def recover_processing_dir(self) -> int:
    """Move any orphaned files in processing/ back to new/ for reprocessing.

    Returns the count of recovered files. Called on daemon startup.
    """
    recovered = 0
    for orphan in list(self.processing_dir.glob("*")):
        if orphan.is_file():
            dest = self.new_dir / orphan.name
            # Avoid name collision
            if dest.exists():
                dest = self.new_dir / f"{orphan.stem}_recovered{orphan.suffix}"
            shutil.move(str(orphan), str(dest))
            logger.warning("Recovered orphaned file from processing/: %s", orphan.name)
            recovered += 1
    return recovered
```

### Index Integrity Check Implementation

Create `src/llm_wiki/startup.py` (NEW file):

```python
"""Daemon startup checks: inbox recovery + index integrity."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# These 4 JSON indexes are always required
_REQUIRED_INDEX_FILES = [
    "index/fulltext.json",
    "index/metadata.json",
    "index/backlinks.json",
    "index/graph_edges.json",
]
# Vector index files — only checked when vector_search is enabled
_VECTOR_INDEX_FILES = [
    "index/vector_index.faiss",
    "index/vector_meta.json",
]


def check_index_integrity(wiki_base: Path, check_vector: bool = True) -> list[str]:
    """Return list of missing or zero-byte index file paths relative to wiki_base.

    Existence + non-empty check only — no parsing.
    """
    files_to_check = list(_REQUIRED_INDEX_FILES)
    if check_vector:
        files_to_check.extend(_VECTOR_INDEX_FILES)

    corrupt = []
    for rel_path in files_to_check:
        path = wiki_base / rel_path
        if not path.exists() or path.stat().st_size == 0:
            corrupt.append(rel_path)
            logger.warning("Index integrity check failed: %s", rel_path)
    return corrupt
```

### WikiDaemon.start() Integration

Modify `WikiDaemon.start()` in `src/llm_wiki/daemon/main.py`. Insert this block BEFORE `self.scheduler.start()` (after all `scheduler.add_job()` calls, before the final `scheduler.start()`):

```python
# Startup recovery: move orphaned processing/ files back to inbox
from llm_wiki.ingest.watcher import InboxWatcher
watcher = InboxWatcher(inbox_dir=wiki_base / "inbox")
recovered = watcher.recover_processing_dir()
if recovered:
    logger.warning("Startup inbox recovery: moved %d orphaned file(s) back to inbox/new/", recovered)

# Index integrity check: trigger synchronous rebuild if corruption detected
from llm_wiki.startup import check_index_integrity
from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob
corrupt_files = check_index_integrity(wiki_base)
if corrupt_files:
    logger.warning(
        "Index integrity check failed for %d file(s): %s — triggering synchronous rebuild",
        len(corrupt_files), corrupt_files,
    )
    try:
        job = IndexRebuildJob(wiki_base=wiki_base)
        result = job.execute()
        logger.info("Synchronous index rebuild complete: %s", result)
    except Exception as e:
        logger.error("Synchronous index rebuild failed: %s — starting with potentially stale indexes", e)
else:
    logger.info("Index integrity check passed")
```

### Prerequisite: Story 1.1

Story 1.1 must be complete before this story. Specifically:
- `IndexRebuildJob` must have the `wiki_base` kwarg working correctly so the synchronous rebuild path here works
- The atomic write fixes in Story 1.1 are what make the integrity check meaningful — without atomic writes, "passes integrity check" doesn't guarantee non-corruption

### Project Structure — Files to Modify / Create

```
src/llm_wiki/
├── startup.py                  NEW — IndexIntegrityCheck logic
├── ingest/
│   └── watcher.py              UPDATE — add recover_processing_dir()
└── daemon/
    └── main.py                 UPDATE — call recovery + integrity check in start()
```

### Testing

**Use `wiki_root` fixture** (from `conftest.py`) — it creates a fully initialized `wiki_system/` structure.

**Test file:** `tests/unit/test_startup.py` (new) — test `check_index_integrity()` directly.

**Test file:** `tests/unit/test_inbox_watcher.py` — add:

```python
def test_recover_processing_dir_moves_files_to_new(self, temp_dir):
    inbox_dir = temp_dir / "inbox"
    watcher = InboxWatcher(inbox_dir=inbox_dir)
    # Create an orphaned file in processing/
    orphan = watcher.processing_dir / "orphaned.md"
    orphan.write_text("content", encoding="utf-8")
    recovered = watcher.recover_processing_dir()
    assert recovered == 1
    assert (watcher.new_dir / "orphaned.md").exists()
    assert not orphan.exists()

def test_recover_processing_dir_empty_returns_zero(self, temp_dir):
    watcher = InboxWatcher(inbox_dir=temp_dir / "inbox")
    assert watcher.recover_processing_dir() == 0
```

**Test file:** `tests/unit/test_startup.py` (new):

```python
def test_check_index_integrity_passes_with_all_files(wiki_root):
    """No corruption when all index files exist and are non-empty."""
    index_dir = wiki_root / "index"
    index_dir.mkdir(exist_ok=True)
    for name in ["fulltext.json", "metadata.json", "backlinks.json", "graph_edges.json"]:
        (index_dir / name).write_text("{}", encoding="utf-8")
    result = check_index_integrity(wiki_root, check_vector=False)
    assert result == []

def test_check_index_integrity_detects_missing_file(wiki_root):
    index_dir = wiki_root / "index"
    index_dir.mkdir(exist_ok=True)
    # Only write some files, not fulltext.json
    for name in ["metadata.json", "backlinks.json", "graph_edges.json"]:
        (index_dir / name).write_text("{}", encoding="utf-8")
    result = check_index_integrity(wiki_root, check_vector=False)
    assert "index/fulltext.json" in result

def test_check_index_integrity_detects_zero_byte_file(wiki_root):
    index_dir = wiki_root / "index"
    index_dir.mkdir(exist_ok=True)
    for name in ["fulltext.json", "metadata.json", "backlinks.json", "graph_edges.json"]:
        (index_dir / name).write_text(
            "" if name == "fulltext.json" else "{}", encoding="utf-8"
        )
    result = check_index_integrity(wiki_root, check_vector=False)
    assert "index/fulltext.json" in result
```

### Critical Anti-Patterns to Avoid

- **Do not** parse index files during the integrity check — existence + non-empty is sufficient and fast
- **Do not** crash the daemon if the synchronous rebuild fails — log and continue
- **Do not** run the scheduler before recovery — scheduler must start after all startup checks complete
- **Do not** create a new `InboxWatcher` inside `WikiDaemon.start()` differently from how it's used in `run_inbox_scan()` — use the same `wiki_base / "inbox"` path

### References

- Orphaned processing dir behavior: `src/llm_wiki/ingest/watcher.py:89-117`
- `WikiDaemon.start()` scheduler start call: `src/llm_wiki/daemon/main.py:197`
- `IndexRebuildJob` (must be complete from Story 1.1): `src/llm_wiki/daemon/jobs/index_rebuild.py`
- Architecture: "Startup Init Sequence" and NFR-R1, NFR-R3, NFR-R4

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
