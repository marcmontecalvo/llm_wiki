# Story 1.1: Atomic Index Writes and Write Mutex

Status: ready-for-dev

## Story

As a wiki operator,
I want all index files written atomically and protected by a per-index mutex,
so that daemon crashes never corrupt indexes and concurrent daemon workers never produce inconsistent index state.

## Acceptance Criteria

1. **Given** any index `save()` method is called **When** it writes to disk **Then** it uses the tmp→`os.replace` pattern: write to `NamedTemporaryFile` in the same directory, then `os.replace(tmp, target)`. No index `save()` method uses `open(path, 'w')` directly.

2. **Given** `WikiQuery` is initialized **When** the instance is created **Then** it maintains a `dict[str, threading.Lock]` keyed by the three incrementally-written index names: `"fulltext"`, `"vector"`, `"metadata"`. `backlinks` and `graph_edges` are **not** in `_index_locks` — they are derived/computed indexes written only by `IndexRebuildJob` during full rebuilds, never incrementally per `add_page()`/`remove_page()`. Their rebuild-time exclusivity is guaranteed by `IndexRebuildJob` holding all three WikiQuery locks (blocking all incremental writes) for the duration of the rebuild.

3. **Given** any index write is triggered via `WikiQuery` methods (`add_page`, `remove_page`) **When** the write begins **Then** the per-index lock is acquired before calling `save()` and released after — even if `save()` raises.

4. **Given** `IndexRebuildJob` runs its full rebuild sweep **When** it executes **Then** it acquires all index locks before starting the sweep and releases all after completion. It is the only code path that bypasses `WikiQuery` methods and directly calls index `save()` — all other callers go through `WikiQuery`. `IndexRebuildJob.execute()` must call `rebuild_from_pages()` and `save()` directly on each index instance; it must never call `WikiQuery.rebuild_indexes()` or `WikiQuery.save_indexes()`, which would attempt to re-acquire already-held non-reentrant locks and deadlock.

5. **Given** two daemon workers attempt to write the same index simultaneously **When** the second arrives at the lock **Then** it blocks until the first completes — no data race, no silent corruption.

6. **Given** a process crash occurs mid-write to any index file **When** the service restarts **Then** no index file is in a partially-written state — the old file remains intact until `os.replace` succeeds atomically.

## Tasks / Subtasks

- [ ] Fix atomic writes in all 5 JSON-based index `save()` methods (AC: 1, 6)
  - [ ] `src/llm_wiki/index/fulltext.py` — `save()`
  - [ ] `src/llm_wiki/index/metadata.py` — `save()`
  - [ ] `src/llm_wiki/index/backlinks.py` — `save()`
  - [ ] `src/llm_wiki/index/graph_edges.py` — `save()`
- [ ] Fix atomic writes in `VectorIndex` (AC: 1, 6)
  - [ ] `save()` — atomic for both `.faiss` file and `vector_meta.json`
  - [ ] `_save_index_to_disk()` — same atomic pattern
  - [ ] Rename `remove_document()` → `remove_document_in_memory()` — removes from in-memory state only, no disk write
  - [ ] Keep `remove_document()` as a wrapper: calls `remove_document_in_memory()` then `_save_index_to_disk()` — preserves existing caller behavior
  - [ ] Update `WikiQuery.remove_page()` to call `remove_document_in_memory()` instead of `remove_document()`, then save under lock
- [ ] Add `_index_locks` registry to `WikiQuery` (AC: 2)
  - [ ] `__init__`: add `self._index_locks: dict[str, threading.Lock]` with 5 keys
  - [ ] Add `acquire_all_locks()` method
  - [ ] Add `release_all_locks()` method
  - [ ] Add `reload_vector_index()` method (loads new FAISS file into `self.vector_index`)
- [ ] Wrap save calls with locks in `WikiQuery` methods (AC: 3)
  - [ ] `add_page()` — call `save()` on all 3 indexes after in-memory update, each locked
  - [ ] `remove_page()` — same
  - [ ] `save_indexes()` — wrap each save with its lock
  - [ ] `rebuild_indexes()` — wrap each save with its lock
- [ ] Refactor `IndexRebuildJob` to use lock protocol (AC: 4, 5)
  - [ ] Add `wiki: WikiQuery | None = None` optional kwarg to `__init__`
  - [ ] `execute()`: call `self.wiki_query.acquire_all_locks()` before any rebuild, `release_all_locks()` in `finally`, then `reload_vector_index()` after release
- [ ] Write tests covering all ACs (see Dev Notes → Testing)

## Dev Notes

### Current State — What Needs to Change

**Non-atomic saves (all must be fixed):**

| File | Method | Problem |
|------|---------|---------|
| `src/llm_wiki/index/fulltext.py:155` | `save()` | `index_file.open("w")` — non-atomic |
| `src/llm_wiki/index/metadata.py:208` | `save()` | `index_file.open("w")` — non-atomic |
| `src/llm_wiki/index/backlinks.py:362` | `save()` | `index_file.open("w")` — non-atomic |
| `src/llm_wiki/index/graph_edges.py:401` | `save()` | `index_file.open("w")` — non-atomic |
| `src/llm_wiki/index/vector.py:251` | `save()` | `meta_path.open("w")` + `faiss.write_index()` — both non-atomic |
| `src/llm_wiki/index/vector.py:199` | `_save_index_to_disk()` | same non-atomic writes as `save()` |

**No mutex:** `WikiQuery` (`src/llm_wiki/query/search.py`) has no `_index_locks` dict. `add_page()`/`remove_page()` update in-memory state only — they do NOT call `save()` currently. After this story they must: update in-memory state, then acquire lock, then save.

**IndexRebuildJob divergence from architecture:** `IndexRebuildJob.__init__()` currently creates its own `WikiQuery` — no injected singleton. The architecture targets injection via `wiki: WikiQuery | None = None`. For this story, add the kwarg but keep backward compat: if `wiki` is None, create a new one from `wiki_base`.

### Reference Implementation — Atomic Write Pattern

The only existing atomic write in the codebase is `JobExecutionStore._save()` at `src/llm_wiki/daemon/execution_store.py:170-177`:

```python
def _save(self, history: JobExecutionHistory) -> None:
    path = self._path(history.job_name)
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(history.to_dict(), indent=2, default=str), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.error("Failed to save execution history for %s: %s", history.job_name, exc)
```

Use `path.with_suffix(".tmp")` (same dir — `os.replace` is atomic only when src and dst are on the same filesystem). For the 4 JSON indexes, adapt directly from this pattern.

**Standard pattern for JSON index save:**
```python
import os
import tempfile

def save(self) -> None:
    index_file = self.index_dir / "fulltext.json"
    data = {"inverted_index": self.inverted_index, "documents": self.documents}
    with tempfile.NamedTemporaryFile(
        "w", dir=self.index_dir, delete=False, suffix=".tmp", encoding="utf-8"
    ) as f:
        json.dump(data, f, indent=2)
        tmp_path = f.name
    os.replace(tmp_path, index_file)
    logger.info(f"Saved fulltext index ({len(self.documents)} documents)")
```

**Vector index atomic save — FAISS file + meta JSON both need it:**
```python
def save(self) -> None:
    ...
    import faiss, numpy as np, os, tempfile

    # Build FAISS index
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    # Atomic FAISS write: write to tmp, then replace
    faiss_path = self.index_dir / "vector_index.faiss"
    with tempfile.NamedTemporaryFile(
        dir=self.index_dir, delete=False, suffix=".tmp"
    ) as f:
        tmp_faiss = f.name
    faiss.write_index(index, tmp_faiss)
    os.replace(tmp_faiss, faiss_path)

    # Atomic meta JSON write
    meta_path = self.index_dir / "vector_meta.json"
    with tempfile.NamedTemporaryFile(
        "w", dir=self.index_dir, delete=False, suffix=".tmp", encoding="utf-8"
    ) as f:
        json.dump(self.doc_meta, f, indent=2)
        tmp_meta = f.name
    os.replace(tmp_meta, meta_path)
```

Apply the same pattern to `_save_index_to_disk()` — it has identical save logic.

### WikiQuery Mutex Implementation

```python
# src/llm_wiki/query/search.py
import threading

class WikiQuery:
    def __init__(self, wiki_base=None, index_dir=None):
        ...
        # Central lock registry — one lock per index file
        # Three incrementally-written indexes only. backlinks and graph_edges are
        # rebuild-only (derived indexes) — they are never written by add_page()/remove_page().
        self._index_locks: dict[str, threading.Lock] = {
            "fulltext": threading.Lock(),
            "vector": threading.Lock(),
            "metadata": threading.Lock(),
        }

    def acquire_all_locks(self) -> None:
        """Acquire all index locks. Used by IndexRebuildJob before full rebuild."""
        for lock in self._index_locks.values():
            lock.acquire()

    def release_all_locks(self) -> None:
        """Release all index locks. Called in IndexRebuildJob.execute() finally block."""
        for lock in self._index_locks.values():
            lock.release()

    def reload_vector_index(self) -> None:
        """Reload FAISS index from disk into memory. Called after IndexRebuildJob completes."""
        with self._index_locks["vector"]:
            self.vector_index.load()

    def add_page(self, page_id, title, content, metadata):
        domain = metadata.get("domain", "general")
        self.metadata_index.add_page(page_id, metadata)
        self.fulltext_index.add_document(page_id, title, content, domain)
        self.vector_index.add_document(page_id, title, content, domain)
        with self._index_locks["metadata"]:
            self.metadata_index.save()
        with self._index_locks["fulltext"]:
            self.fulltext_index.save()
        with self._index_locks["vector"]:
            self.vector_index.save()

    def remove_page(self, page_id):
        self.metadata_index.remove_page(page_id)
        self.fulltext_index.remove_document(page_id)
        self.vector_index.remove_document(page_id)
        # Note: VectorIndex.remove_document() already calls _save_index_to_disk()
        # That call is now also atomic, but NOT yet lock-protected.
        # Fix: remove_document() should NOT auto-save; WikiQuery owns the save.
        with self._index_locks["metadata"]:
            self.metadata_index.save()
        with self._index_locks["fulltext"]:
            self.fulltext_index.save()
        with self._index_locks["vector"]:
            self.vector_index.save()

    def save_indexes(self) -> None:
        with self._index_locks["metadata"]:
            self.metadata_index.save()
        with self._index_locks["fulltext"]:
            self.fulltext_index.save()
        with self._index_locks["vector"]:
            self.vector_index.save()

    def rebuild_indexes(self):
        metadata_count = self.metadata_index.rebuild_from_pages(self.wiki_base)
        fulltext_count = self.fulltext_index.rebuild_from_pages(self.wiki_base)
        vector_count = self.vector_index.rebuild_from_pages(self.wiki_base)
        with self._index_locks["metadata"]:
            self.metadata_index.save()
        with self._index_locks["fulltext"]:
            self.fulltext_index.save()
        with self._index_locks["vector"]:
            self.vector_index.save()
        return metadata_count, fulltext_count, vector_count
```

**VectorIndex — in-memory vs persisted removal:**

Rename `remove_document()` → `remove_document_in_memory()` (removes from in-memory structures only, no disk write). Keep `remove_document()` as a backward-compatible wrapper:

```python
def remove_document(self, doc_id: str) -> None:
    """Remove document and persist immediately. For direct callers outside WikiQuery."""
    self.remove_document_in_memory(doc_id)
    self._save_index_to_disk()
```

`WikiQuery.remove_page()` calls `remove_document_in_memory()` directly, then saves under lock. This ensures:
- External callers of `VectorIndex.remove_document()` retain existing save behavior (no silent regression)
- `WikiQuery` owns the save cycle and lock acquisition
- The contract is impossible to misuse: the method name states exactly what it does

### IndexRebuildJob Refactor

```python
# src/llm_wiki/daemon/jobs/index_rebuild.py
class IndexRebuildJob:
    def __init__(self, wiki_base=None, wiki=None):
        self.wiki_base = wiki_base or Path("wiki_system")
        # Accept injected WikiQuery singleton (Sprint 1.4 will inject app.state.wiki)
        # Fall back to creating a local instance for backward compat
        self.wiki_query = wiki if wiki is not None else WikiQuery(wiki_base=self.wiki_base)
        self.backlink_index = BacklinkIndex(index_dir=self.wiki_base / "index")
        self.graph_edge_index = GraphEdgeIndex(index_dir=self.wiki_base / "index")

    def execute(self):
        logger.info("Starting index rebuild job")
        self.wiki_query.acquire_all_locks()
        try:
            metadata_count, fulltext_count, vector_count = self.wiki_query.rebuild_indexes()
            # rebuild_indexes() saves metadata/fulltext/vector with their individual locks,
            # but acquire_all_locks() is already held — that's fine (locks are not reentrant by default)
            # WAIT — this is a problem: acquire_all_locks() holds the locks, then rebuild_indexes()
            # tries to re-acquire the same locks → DEADLOCK.
            ...
        finally:
            self.wiki_query.release_all_locks()
```

**DEADLOCK HAZARD — Read this carefully:**

`acquire_all_locks()` acquires all locks. Then `rebuild_indexes()` calls `self.metadata_index.save()` inside a `with self._index_locks["metadata"]` block — which tries to acquire the same non-reentrant `threading.Lock` → **deadlock**.

**Resolution:** `IndexRebuildJob` takes the exclusive path. It calls `acquire_all_locks()` and then calls index save methods DIRECTLY on index instances (bypassing `WikiQuery`'s lock-wrapped `save_indexes()`). The pattern is:

```python
def execute(self):
    self.wiki_query.acquire_all_locks()
    try:
        # Rebuild all indexes (in-memory only — do NOT call save() yet)
        metadata_count = self.wiki_query.metadata_index.rebuild_from_pages(self.wiki_base)
        fulltext_count = self.wiki_query.fulltext_index.rebuild_from_pages(self.wiki_base)
        vector_count = self.wiki_query.vector_index.rebuild_from_pages(self.wiki_base)
        backlink_count = self.backlink_index.rebuild_from_pages(self.wiki_base)
        graph_edge_count = self.graph_edge_index.rebuild_from_pages(self.wiki_base)

        # Save directly — locks are already held by acquire_all_locks()
        self.wiki_query.metadata_index.save()
        self.wiki_query.fulltext_index.save()
        self.wiki_query.vector_index.save()
        self.backlink_index.save()
        self.graph_edge_index.save()

        return {..., "status": "success"}
    except Exception as e:
        logger.error(f"Index rebuild failed: {e}", exc_info=True)
        return {..., "status": "error", "error": str(e)}
    finally:
        self.wiki_query.release_all_locks()

    # After releasing locks, reload FAISS into memory
    self.wiki_query.reload_vector_index()
```

**Consequence for `rebuild_indexes()` in WikiQuery:** This method is now only called from paths that do NOT hold the locks (e.g., direct API calls). It should NOT be called from `IndexRebuildJob`. Remove `rebuild_indexes()` usage from `IndexRebuildJob.execute()` and replace with the direct index method calls shown above.

Also update `run_index_rebuild()` convenience function at the bottom of `index_rebuild.py` accordingly.

### Project Structure — Files to Modify

All files are **UPDATE** (modifying existing code, not creating new):

```
src/llm_wiki/
├── index/
│   ├── fulltext.py        UPDATE — save() atomic
│   ├── metadata.py        UPDATE — save() atomic
│   ├── backlinks.py       UPDATE — save() atomic
│   ├── graph_edges.py     UPDATE — save() atomic
│   └── vector.py          UPDATE — save() and _save_index_to_disk() atomic; remove auto-save from remove_document()
├── query/
│   └── search.py          UPDATE — _index_locks, acquire/release/reload methods, lock-wrapped saves
└── daemon/jobs/
    └── index_rebuild.py   UPDATE — optional wiki kwarg, acquire_all_locks() protocol
```

### Testing

**Use `temp_dir` fixture** (not `wiki_root`) for index tests — these don't need a full wiki structure, just an index dir.

**Test file to add tests to / what to test:**

`tests/unit/test_fulltext_index.py` — add:
```python
def test_save_is_atomic(self, temp_dir):
    """Crash mid-write leaves old file intact, not corrupt."""
    idx = FulltextIndex(index_dir=temp_dir)
    idx.add_document("p1", "Title", "Content", "general")
    idx.save()
    original = (temp_dir / "fulltext.json").read_text()

    # Simulate: verify no .tmp file left behind after save
    idx.add_document("p2", "Title 2", "Content 2", "general")
    idx.save()
    assert not list(temp_dir.glob("*.tmp")), "No tmp files should remain after save"
    assert "p2" in (temp_dir / "fulltext.json").read_text()
```

Replicate for `metadata`, `backlinks`, `graph_edges`.

`tests/unit/test_vector_index.py` — add atomic write test for `.faiss` and `vector_meta.json`.

`tests/unit/test_wiki_query.py` — add:
```python
def test_has_index_locks(self, wiki_query):
    locks = wiki_query._index_locks
    assert set(locks) == {"fulltext", "vector", "metadata"}
    import threading
    assert all(isinstance(v, threading.Lock) for v in locks.values())
    # backlinks and graph_edges are rebuild-only — must NOT be in _index_locks
    assert "backlinks" not in locks
    assert "graph_edges" not in locks

def test_add_page_saves_to_disk(self, wiki_query, temp_dir):
    """add_page() persists immediately — not just in-memory."""
    metadata = {"id": "p1", "title": "T", "domain": "d", "tags": []}
    wiki_query.add_page("p1", "T", "content", metadata)
    assert (wiki_query.index_dir / "fulltext.json").exists()
    assert (wiki_query.index_dir / "metadata.json").exists()

def test_concurrent_writes_do_not_race(self, wiki_query):
    """Two threads writing the same index do not produce torn files."""
    import threading, time
    errors = []
    def worker(i):
        try:
            metadata = {"id": f"p{i}", "title": f"T{i}", "domain": "d", "tags": []}
            wiki_query.add_page(f"p{i}", f"T{i}", "content", metadata)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors
```

`tests/unit/test_index_rebuild_job.py` — add:
```python
def test_acquire_all_locks_before_rebuild(self, wiki_base):
    """IndexRebuildJob holds all locks during rebuild."""
    import threading
    job = IndexRebuildJob(wiki_base=wiki_base)
    lock_states = {}
    original_acquire = job.wiki_query.acquire_all_locks

    def capture_acquire():
        original_acquire()
        lock_states["locked_during_rebuild"] = all(
            not lock.acquire(blocking=False)  # returns False if already locked
            for lock in job.wiki_query._index_locks.values()
        )
        # Re-lock since we just tried to acquire
    job.wiki_query.acquire_all_locks = capture_acquire
    job.execute()
    assert lock_states.get("locked_during_rebuild", False)
```

### Critical Anti-Patterns to Avoid

- **Do not** use `with open(path, 'w')` anywhere in index saves — this is the bug being fixed
- **Do not** call `VectorIndex.remove_document()` from `WikiQuery.remove_page()` — use `remove_document_in_memory()` instead so `WikiQuery` owns the save cycle under lock. `remove_document()` (the public wrapper) is for external callers only.
- **Do not** call `rebuild_indexes()` from `IndexRebuildJob.execute()` — deadlock via double lock acquisition
- **Do not** change `threading.Lock()` to `threading.RLock()` to "fix" the deadlock — the deadlock must be resolved by separating the lock-holding path (IndexRebuildJob) from the lock-acquiring path (WikiQuery methods)
- **Do not** add new index `save()` calls anywhere that bypass the lock protocol

### References

- Atomic write reference: `src/llm_wiki/daemon/execution_store.py:170-177`
- Current non-atomic fulltext save: `src/llm_wiki/index/fulltext.py:155-167`
- Current non-atomic metadata save: `src/llm_wiki/index/metadata.py:208-224`
- Current non-atomic backlinks save: `src/llm_wiki/index/backlinks.py:362-378`
- Current non-atomic graph_edges save: `src/llm_wiki/index/graph_edges.py:401-412`
- Current non-atomic vector save (both methods): `src/llm_wiki/index/vector.py:199-249`, `251-288`
- VectorIndex.remove_document() auto-save to remove: `src/llm_wiki/index/vector.py:121`
- WikiQuery (no mutex today): `src/llm_wiki/query/search.py:17-172`
- IndexRebuildJob (no injection today): `src/llm_wiki/daemon/jobs/index_rebuild.py:14-85`
- Architecture: Index Write Concurrency section
- Project context: Critical Anti-Patterns → "Atomic writes — the only safe index save pattern"
- Project context: Critical Anti-Patterns → "Concurrent index writes — no mutex exists yet"

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
