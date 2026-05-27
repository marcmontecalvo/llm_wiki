# Story HF.2: Workspace Fact Storage and History

Status: backlog

## Story

As a wiki operator,
I want fact storage to be machine-readable, append-only, and crash-safe,
so that fact history is reliable and concurrent writes never corrupt data.

**Prerequisites:** Story HF.1 must be complete — this story deepens the storage layer added in HF.1 with proper history management, concurrency controls, and integrity checks.

## Acceptance Criteria

1. **Given** a workspace facts directory **When** audited **Then** the current fact state is machine-readable (JSON/JSONL) without any markdown parsing — no `.md` files store fact data.

2. **Given** a fact is written or updated **When** the store records it **Then** the append-only history JSONL file captures all previous versions — no old versions are ever overwritten or lost.

3. **Given** a fact write **When** it is persisted **Then** it uses the temp file + `os.replace` pattern (AC: 1, HF.1 AC: 9).

4. **Given** two concurrent writes targeting the same fact in the same workspace **When** they arrive **Then** per-workspace and per-fact locks prevent data races — one blocks until the other completes.

5. **Given** the daemon starts **When** the fact store initializes ** Then** it checks that the `index.json` per workspace exists and is valid; if corrupt or missing, it encounters a known pathway (logs a warning, won't serve) rather than crashing.

## Tasks / Subtasks

- [ ] Enhance `WorkspaceFactStore` with append-only history (AC: 2, 3)
  - [ ] Fact history stored in `{wiki_base}/workspaces/{workspace_id}/facts/history/{fact_key_hash}.jsonl`
  - [ ] Each JSONL line is a full `KnowledgeFact` serialized as JSON — no partial state
  - [ ] `_write_entry(workspace_id: str, fact_key: str, fact: KnowledgeFact)` appends atomically (temp→os.replace on JSONL)
  - [ ] `_read_history(workspace_id: str, fact_key: str) -> list[KnowledgeFact]` reads all history entries
  - [ ] `_latest_entry(workspace_id: str, fact_key: str) -> KnowledgeFact | None` reads last line
- [ ] Implement per-fact locking (AC: 4)
  - [ ] `self._fact_locks: dict[tuple[str, str], threading.Lock]` — lazy initialization
  - [ ] `put_fact()`: acquires `(workspace_id, fact_key)` lock before reading version, computing new version, writing
  - [ ] Lock is released via `finally` block — even on exception
  - [ ] Per-workspace lock (coarse-grained): used for index file read-modify-write
  - [ ] Table of lock granularity: per-fact = fine-grained parallelism for different keys; per-workspace = coarse for index operations
- [ ] Implement startup integrity check (AC: 5)
  - [ ] `_integrity_check(workspace_id: str) -> None` — validates index.json structure
  - [ ] `index.json` expected shape: `{"fact_key": {"path": "relative", "version": int, "updated_at": "ISO8601"}}`
  - [ ] If `index.json` missing: creates empty dict, writes atomically, logs warning `"workspace_facts_index_missing"`
  - [ ] If `index.json` corrupt (not valid JSON): logs error, does NOT crash — starts with empty facts for that workspace; subsequent queries include a degraded signal rather than blocking the service (consistent with AC:5 "known pathway")
  - [ ] `_scan_history_files(workspace_id: str) -> None` — rebuilds index from JSONL if index is missing but history exists
    - [ ] Reads each JSONL, takes last entry per fact, rebuilds index
    - [ ] Called from `_scan_or_build_index()` — runs on startup when index is missing
  - [ ] Add `recovery_count` to warn log if rebuild finds data in history that wasn't in index
- [ ] Implement workspace directory initialization (AC: 5)
  - [ ] `ensure_workspace(workspace_id: str) -> Path` creates directory structure atomically
  - [ ] Structure: `facts/`, `facts/categories/`, `facts/history/`
  - [ ] Calls `os.makedirs(path, exist_ok=True)` before any file operations
  - [ ] Idempotent — no error if directory already exists
- [ ] Remove any markdown-based fact access from existing code (AC: 1)
  - [ ] Audit all callers: verify no code reads/writes facts as `.md` files
  - [ ] Facts are purely JSON/JSONL — pages remain in `/pages/` as markdown
- [ ] Write tests (`tests/unit/test_facts_storage.py` — AC: 1–5)
  - [ ] Test append-only history: write v1, write v2, read history returns 2 entries
  - [ ] Test atomic write: mock `os.replace` failure, verify old data preserved
  - [ ] Test per-fact lock: concurrent writes to same key, verify monotonic version
  - [ ] Test per-fact lock: concurrent writes to different keys, verify parallelism
  - [ ] Test integrity check: corrupt index.json → no crash, logs warning
  - [ ] Test missing index.json → rebuilds from history files
  - [ ] Test workspace initialization: empty workspace gets directory structure
  - [ ] Test idempotency: double init does not overwrite existing data

## Dev Notes

### Lock Singleton (Wiki-wide)

```python
class WorkspaceFactStore:
    """Thread-safe, file-backed fact store scoped by workspace_id.

    Each workspace gets:
      - A directory: wiki_system/workspaces/{workspace_id}/facts/
      - An index:   facts/index.json (mapping key -> metadata)
      - A history:  facts/history/{hash}.jsonl (append-only version log)

    Concurrency:
      - Per-fact locks for write operations on specific {workspace_id, fact_key} tuples.
      - Per-workspace lock for coarse index writes.
      - Read operations are lock-free (JSONL is append-only, atomic line reads).
    """

    def __init__(self, wiki_base: str | None = None):
        self._wiki_base = wiki_base or os.environ.get("WIKI_ROOT", "wiki_system")
        self._fact_locks: dict[tuple[str, str], threading.Lock] = {}
        self._workspace_locks: dict[str, threading.Lock] = {}
        self._lock_lock = threading.Lock()  # protects dict creation itself

    def _create_lock(self, key: object) -> threading.Lock:
        # Thread-safe lazy dict insertion under a global lock
        ...

    def put_fact(self, workspace_id: str, write_req: KnowledgeFactWriteRequest) -> KnowledgeFactWriteResponse:
        # workspace_id extracted from route path, not from request body
        lock = self._create_lock((workspace_id, write_req.key))
        with lock:
            # ... validate, compute version, write
            ...
```
