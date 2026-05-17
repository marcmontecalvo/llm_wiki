# Session Report — 2026-05-16

**Session scope**: Phase 1.1 — Vector/Semantic Search implementation and full Phase 0 lint/error-hierarchy clean-up
**Commit**: `f1a2976` — "feat: Phase 1.1 — Vector/Semantic Search, error handling consolidation, lint cleanup"
**Branch**: main
**Final state**: 1106 tests pass, 0 ruff errors, mypy clean (only expected `import-untyped` warnings for third-party libs without stubs)

---

## What Was Accomplished

### 1. Vector/Semantic Search — `src/llm_wiki/index/vector.py` (NEW, 407 lines)

The primary deliverable: a FAISS-backed dense vector index for semantic retrieval, following the same save/load/rebuild pattern as `FulltextIndex`.

**Why FAISS + sentence-transformers?**
- FAISS (`faiss-cpu`) is the standard CPU-native library for exact/approximate nearest-neighbor search on dense vectors. `IndexFlatL2` gives exact brute-force L2 distance, which is correct for small-to-medium corpora (< ~100k pages). No approximation error.
- `sentence-transformers` with `all-MiniLM-L6-v2` is the canonical lightweight model for English semantic embedding: 384 dimensions, ~80MB download, runs on CPU, widely understood by the open-source community. No GPU required. Inference time: ~5ms per document on modern CPU.
- Both are optional (`llm-wiki[vector]`): the module detects their absence at import time and silently no-ops. The system continues to function (keyword search still works) without the vector extras.

**Architecture decisions made:**

| Decision | Rationale |
|----------|-----------|
| `IndexFlatL2` (exact, not HNSW approximate) | Correctness over speed for small corpora. HNSW would only matter at >10k pages with <100ms latency requirements. |
| Re-embed on `remove_document()` | FAISS `IndexFlatL2` has no per-vector deletion API. The entire index must be rebuilt. We store the original clean text (`_embedded_texts`) to avoid re-reading disk. |
| Lazy model loading (`_ensure_model()`) | Model download on first use, not on import. Avoids slowing CLI startup for users who don't use vector search. |
| `_clean_for_embedding()` strips markdown | Embedding `#` headers and `**bold**` markers degrades semantic quality — the model was trained on clean prose, not markdown syntax. |
| Separate `vector_meta.json` + `.faiss` file | Metadata (title, domain, vector_idx) needs to be human-readable for debugging. FAISS binary is compact for vectors. |

**Key implementation subtlety — FAISS API:**

`IndexFlatL2` uses `faiss.write_index()` / `faiss.read_index()`. These are the standard float-vector API.
`IndexBinaryFlat` uses `faiss.write_index_binary()` / `faiss.read_index_binary()`. These are a DIFFERENT API for binary vectors.

An earlier attempt used the binary API with a float index — this caused silent data corruption. The fix: always use `write_index` / `read_index` for `IndexFlatL2`.

**Key implementation subtlety — mypy type ignores:**

```python
# WRONG — type ignore only applies to the assignment, not the method call
model = self._model  # type: ignore[union-attr]
embedding = model.encode(text)  # ← mypy still errors here

# CORRECT — type ignore on the actual method call
embedding = self._model.encode(  # type: ignore[union-attr]
    text, batch_size=1, show_progress_bar=False, normalize_embeddings=True,
)
```

This subtlety applies to three locations in `vector.py`: `search()`, `save()`, and `rebuild_from_pages()`.

**Data structures:**

```python
self.doc_ids: list[str]               # ordered list of page IDs (position = FAISS index position)
self.idx_to_id: dict[int, str]        # FAISS position → page_id
self.id_to_idx: dict[str, int]        # page_id → FAISS position
self.doc_meta: dict[str, dict]        # page_id → {title, domain, vector_idx}
self._embedded_texts: dict[str, str]  # page_id → clean text used for embedding
self._model: Any | None               # lazy-loaded SentenceTransformer
```

**Persistence format:**

```
wiki_system/index/
├── vector_index.faiss   # FAISS binary, IndexFlatL2, float32, 384 dimensions
└── vector_meta.json     # {page_id: {title, domain, vector_idx}}
```

**Public interface:**

```python
vi = VectorIndex(index_dir=Path("wiki_system/index"))
vi.add_document("page_id", "Title", "Content markdown", "domain")
vi.remove_document("page_id")       # rebuilds FAISS index without this doc
vi.search("query", domain="tech", limit=10)  # returns [{page_id, title, domain, score}, ...]
vi.save()                           # embed all docs → write FAISS + meta JSON
vi.load()                           # read meta JSON → populate in-memory dicts
vi.rebuild_from_pages(wiki_base)    # scan all domains/pages/, batch embed, write index
```

---

### 2. WikiQuery Integration — `src/llm_wiki/query/search.py` (MODIFIED)

Integrated `VectorIndex` with **Reciprocal Rank Fusion (RRF)** to merge fulltext and vector results into a single ranked list.

**Why RRF?**

RRF is a simple, parameter-light rank fusion formula from Cormack et al. (2009):

```
score(d) = sum over each ranking: 1 / (k + rank(d) + 1)
```

Where `k=60` is the smoothing constant from the original paper. A document appearing in both fulltext and vector results gets a double contribution. Higher-ranked positions contribute more. The formula:

1. Doesn't require knowing absolute scores from either index — just ordinal rank
2. Is robust to wildly different score scales (BM25 scores and cosine similarities are not comparable)
3. Is proven to outperform simple score merging in TREC benchmarks
4. Is trivially reproducible with no additional dependencies

**Implementation:**

```python
k = 60
rrf_scores: dict[str, float] = {}
for rank, result in enumerate(fulltext_results + vector_results):
    pid = result["page_id"]
    rrf_scores[pid] = rrf_scores.get(pid, 0.0) + 1 / (k + rank + 1)
sorted_page_ids = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
```

**Important mypy gotcha:** `key=rrf_scores.get` causes a mypy overload resolution failure because `dict.get` is overloaded with optional default. Use `key=lambda k: rrf_scores[k]` instead (this is safe because we only sort keys that are in the dict).

**Changes to `WikiQuery`:**

- `__init__`: `self.vector_index = VectorIndex(index_dir=self.index_dir)`
- `_load_indexes()`: `self.vector_index.load()`
- `search()`: RRF fusion of fulltext + vector results
- `add_page()`: `self.vector_index.add_document(...)`
- `remove_page()`: `self.vector_index.remove_document(page_id)`
- `rebuild_indexes()`: `self.vector_index.rebuild_from_pages(self.wiki_base)`
- `save_indexes()`: `self.vector_index.save()`

---

### 3. Index Rebuild Daemon Job — `src/llm_wiki/daemon/jobs/index_rebuild.py` (MODIFIED)

Added vector index rebuild to `IndexRebuildJob.execute()`:

```python
from llm_wiki.index.vector import VectorIndex
vector_index = VectorIndex(index_dir=self.wiki_base / "index")
vector_count = vector_index.rebuild_from_pages(self.wiki_base)
```

Returns `vector_count` in the result dict alongside existing fulltext/metadata counts.

---

### 4. Optional Dependency Declaration — `pyproject.toml` (MODIFIED)

```toml
[project.optional-dependencies]
vector = [
    "faiss-cpu>=1.8",
    "sentence-transformers>=3.0",
]
```

Install with: `pip install llm-wiki[vector]` or `uv add llm-wiki[vector]`

`uv.lock` was regenerated to include the transitive closure of `faiss-cpu` and `sentence-transformers` dependencies (numpy, huggingface-hub, tokenizers, transformers, etc.).

---

### 5. Test Suite — `tests/unit/test_vector_index.py` (NEW, 252 lines)

Two test classes:

**`TestVectorIndexBasic`** (5 tests, no optional deps required):
Tests all graceful-fallback paths — what happens when `sentence-transformers` / `faiss` are not installed. Verified by monkey-patching `_ensure_model` to return `False`.

| Test | What it verifies |
|------|-----------------|
| `test_init` | Clean initial state |
| `test_search_no_model_returns_empty` | Search no-ops without model |
| `test_add_document_no_model_does_nothing` | Add no-ops without model |
| `test_rebuild_no_model_returns_zero` | Rebuild returns 0 without model |
| `test_save_no_model_does_nothing` | Save no-ops without model |

**`TestVectorIndexFull`** (14 tests, requires `faiss-cpu` + `sentence-transformers`):
Skip marker: `@pytest.mark.skipif(not FAISS_AVAILABLE, reason="faiss-cpu not installed")`

| Test | What it verifies |
|------|-----------------|
| `test_add_document` | Metadata stored correctly (title, domain, vector_idx) |
| `test_add_multiple_documents` | All three dicts grow consistently |
| `test_remove_document` | Removal clears all four data structures |
| `test_remove_nonexistent` | No-op on unknown page_id |
| `test_save_and_load` | Round-trip: save → new instance → load → same state |
| `test_load_nonexistent` | No-op when no index files exist |
| `test_rebuild_from_pages` | Scans wiki fixture, indexes 2 docs correctly |
| `test_rebuild_clears_existing` | Pre-existing docs are removed before rebuild |
| `test_rebuild_from_pages_missing_domains` | Returns 0 when wiki dir doesn't exist |
| `test_search_empty_index` | Returns [] on empty index |
| `test_search_with_domain_filter` | Domain filter correctly limits results |
| `test_search_returns_score` | Results include a non-negative `score` field |
| `test_search_limit` | `limit=3` returns ≤ 3 results |
| `test_rebuild_multiple_domains` | Indexes across multiple domain directories |

---

### 6. Error Hierarchy Consolidation — `src/llm_wiki/daemon/errors.py` (CREATED, 65 lines)

Centralized exception hierarchy for the daemon subsystem. Previously exceptions were scattered or used raw `RuntimeError`.

```python
class DaemonError(Exception): ...          # base
class ConfigError(DaemonError): ...        # bad config at runtime
class SchedulerError(DaemonError): ...     # base for scheduler errors
class SchedulerAlreadyRunningError(SchedulerError): ...
class SchedulerNotRunningError(SchedulerError): ...
class JobNotFoundError(SchedulerError): ...
class WorkerPoolError(DaemonError): ...    # base for worker pool errors
class WorkerPoolAlreadyStartedError(WorkerPoolError): ...
class WorkerPoolNotStartedError(WorkerPoolError): ...
class ExecutionError(DaemonError): ...     # job execution recording failures
class GovernanceError(DaemonError): ...    # governance check fatal problems
class IngestionError(DaemonError): ...     # irrecoverable ingestion failures
```

**Naming issue encountered:** Ruff rule N818 requires all Exception subclasses to end in `Error`. Original names were `SchedulerAlreadyRunning`, `WorkerPoolAlreadyStarted`, etc. — all renamed.

When using `Edit(replace_all=True)` to rename exceptions, the ordering matters: renaming `SchedulerAlreadyRunning` while `SchedulerAlreadyRunningError` already exists in the same file creates `SchedulerAlreadyRunningErrorError`. Required careful Edit operations on each name individually.

Updated references in:
- `src/llm_wiki/daemon/scheduler.py`
- `src/llm_wiki/daemon/workers.py`
- `tests/unit/test_scheduler.py`
- `tests/unit/test_workers.py`
- `src/llm_wiki/__init__.py`

---

### 7. Lint and Type Fixes — `src/llm_wiki/cli.py` (MODIFIED)

Multiple ruff violations fixed:

| Rule | Location | Fix |
|------|---------|-----|
| B904 | 2 `except` clauses | `raise SystemExit(1)` → `raise SystemExit(1) from exc` |
| F841 | `config = load_config(...)` | Removed unused assignment — call without binding |
| I001 | Import ordering | `ruff check --fix` auto-corrected |

Mypy fix: Added `cast(MergeStrategy, param)` for 6 Literal type assignments.

---

## Bugs Fixed

### Bug 1: Wrong FAISS API for float index

**Error**: Calling `faiss.write_index_binary(embeddings, path)` on a float `IndexFlatL2`.
`write_index_binary` is for `IndexBinaryFlat` (binary vectors). `IndexFlatL2` requires `write_index`.

**Fix**: `faiss.write_index(index, str(faiss_path))` / `faiss.read_index(str(faiss_path))`

### Bug 2: `write_index` called on numpy array instead of index

**Error**: `faiss.write_index(embeddings, path)` — passed the raw embedding array instead of the FAISS index object.
Must first: `index = faiss.IndexFlatL2(dim)` → `index.add(embeddings)` → `faiss.write_index(index, path)`.

**Fix**: Three-step pattern consistently applied in `save()`, `_save_index_to_disk()`, `rebuild_from_pages()`.

### Bug 3: mypy union-attr error on intermediate variable

**Error**: Assigning `model = self._model  # type: ignore[union-attr]` only suppresses the error on that line. Calling `model.encode()` on the next line still errors.

**Fix**: Apply the type ignore directly to the method call: `self._model.encode(  # type: ignore[union-attr]`.

### Bug 4: RRF sort key causing mypy overload error

**Error**: `sorted(rrf_scores.keys(), key=rrf_scores.get)` — mypy can't resolve which `dict.get` overload this is.

**Fix**: `key=lambda k: rrf_scores[k]` — unambiguous, safe because we only sort keys known to be in the dict.

### Bug 5: Exception class names didn't end in `Error`

**Error**: Ruff N818 blocks commit when exception classes are named `SchedulerAlreadyRunning` (not `Error`-suffixed).

**Fix**: Renamed all 4 classes. Carefully ordered Edit operations to avoid `ErrorError` double-suffixing.

---

## Final Metrics

| Metric | Value |
|--------|-------|
| Tests passing | 1106 |
| Test failures | 0 |
| Ruff errors | 0 |
| Mypy errors (new) | 0 |
| Files created | 3 (vector.py, errors.py, test_vector_index.py) |
| Files modified | ~12 |
| Commit hash | f1a2976 |

---

## Files Created/Modified

| File | Status | Lines | Purpose |
|------|--------|-------|---------|
| `src/llm_wiki/index/vector.py` | CREATED | 407 | FAISS vector index with sentence-transformers |
| `src/llm_wiki/daemon/errors.py` | CREATED | 65 | Daemon exception hierarchy |
| `tests/unit/test_vector_index.py` | CREATED | 252 | Full vector index test coverage |
| `src/llm_wiki/query/search.py` | MODIFIED | — | RRF fusion of fulltext + vector results |
| `src/llm_wiki/daemon/jobs/index_rebuild.py` | MODIFIED | — | Vector rebuild in daemon job |
| `pyproject.toml` | MODIFIED | — | `[vector]` optional extras |
| `uv.lock` | MODIFIED | — | Lock file with transitive vector deps |
| `src/llm_wiki/__init__.py` | MODIFIED | — | Exported daemon error classes |
| `src/llm_wiki/cli.py` | MODIFIED | — | B904/F841/I001 lint fixes |
| `src/llm_wiki/daemon/scheduler.py` | MODIFIED | — | Error class rename |
| `src/llm_wiki/daemon/workers.py` | MODIFIED | — | Error class rename |
| `tests/unit/test_scheduler.py` | MODIFIED | — | Error class rename in tests |
| `tests/unit/test_workers.py` | MODIFIED | — | Error class rename in tests |

Also staged in this commit (created in prior session):
- `src/llm_wiki/config/validator.py` — Config validation at daemon startup
- `src/llm_wiki/daemon/logging_config.py` — Structured logging setup
- `tests/unit/test_config_validator.py` — Config validator tests
- `tests/unit/test_health.py` — Health check endpoint tests
- `tests/unit/test_logging_config.py` — Logging tests
- `docs/Product_Brief.md` — Full product brief with V2-V5 roadmap
- `docs/roadmap-deferred.md` — Dropped/deferred items decision log

---

## Pending Work After This Session

1. **Git push** — `git push` was attempted but failed due to SSH agent communication issue (1Password SSH agent). Commit is clean at HEAD. Fix: restart 1Password agent or push in fresh terminal.

2. **Phase 1.2 / Phase 2** — See `PROJECT_STATUS.md` and `ROADMAP_REMAINING.md` in this directory for what's next.
