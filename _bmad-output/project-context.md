---
project_name: 'llm_wiki'
user_name: 'Marc'
date: '2026-05-16'
sections_completed: ['technology_stack', 'python_rules', 'framework_patterns', 'testing_rules', 'critical_antipatterns', 'data_storage_rules', 'workflow_rules']
existing_patterns_found: 15
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Python**: 3.11+ required (3.12 also tested in CI). Never target 3.10.
- **Package manager**: uv (not pip). Always `uv run <cmd>`, `uv add`, `uv sync`. System `python3` on macOS is often 3.10 — never use it directly.
- **CLI**: Click 8.1+
- **Data validation**: Pydantic 2.0+ (v2 API — use `model_validate`, not `parse_obj`)
- **Daemon**: APScheduler 3.10+ `BackgroundScheduler` + `ThreadPoolExecutor`
- **File watching**: watchdog 3.0+
- **Frontmatter**: python-frontmatter 1.0+
- **LLM client**: openai 1.0+ (OpenAI-compatible; also supports Anthropic/Ollama/LM Studio via `base_url`)
- **Retry logic**: tenacity 8.0+
- **Build**: hatchling via uv
- **Optional — vector search**: faiss-cpu 1.8+ + sentence-transformers 3.0+ (install with `uv sync --extra vector`)
- **Optional — Claude Agent SDK**: claude-agent-sdk (install with `uv sync --extra claude-agent`)
- **CI**: GitHub Actions — Python 3.11 + 3.12 matrix; ruff, mypy, pytest, codecov, uv build

---

## Language-Specific Python Rules

### Environment isolation — principle, not a single fact

Always use `uv run <cmd>` for any Python execution within the project. `uv run` activates the project virtualenv; the ambient `python3`/`pytest`/`mypy` on the shell is untrustworthy (macOS system Python is often 3.10). This extends to: `uv run pytest`, `uv run mypy src/`, `uv run ruff check .`, `uv add` (not `pip install`). Never call bare `python3`, `pytest`, or `mypy` directly.

### Pydantic v2 — treat every API as potentially v1

This project uses Pydantic v2. Agents trained on Pydantic v1 will reach for v1 APIs instinctively. When uncertain about any Pydantic operation, assume it may have changed and check the v2 API. Common v1→v2 migrations:

| v1 (wrong) | v2 (correct) |
|---|---|
| `parse_obj()` | `model_validate()` |
| `.dict()` | `.model_dump()` |
| `.schema()` | `.model_json_schema()` |
| `@validator` | `@field_validator` |
| `@root_validator` | `@model_validator` |
| `__fields__` | `model_fields` |

### `# type: ignore` — placement is semantic, not stylistic

`# type: ignore[code]` suppresses the error on the expression mypy evaluates on that exact line. If the type mismatch is at a method call but the comment is on the variable assignment receiving the result, mypy evaluates the wrong node and the error persists. Place the comment on the line where the actual type mismatch occurs — often the call site, not the assignment.

Always use a specific error code: `# type: ignore[union-attr]`, never bare `# type: ignore` (bare suppresses all future regressions on that line silently).

### Exception chaining — understand the traceback semantics

Ruff B904 enforces `raise NewError(...) from exc` inside `except` blocks. The reason: bare `raise NewError(...)` in an except block drops the original traceback, making debugging impossible. Two valid forms:
- `raise NewError(...) from exc` — chains the original exception (most common)
- `raise NewError(...) from None` — explicitly suppresses chaining (intentional, not a B904 violation)

### mypy config — lenient input, strict correctness

`disallow_untyped_defs = false` means you don't have to annotate every function. It does not mean typing is optional or sloppy. `warn_return_any = true` is also set — returning untyped values from typed functions will still error. Rule: don't add types just to satisfy mypy; when you do add type annotations, make them specific and correct. Expected `import-untyped` warnings for faiss, sentence-transformers, apscheduler — these are known and acceptable.

### Exception naming

Ruff N818 enforces that all `Exception` subclasses must end in `Error` (e.g., `WikiNotFoundError`, `IngestError`). This applies to every custom exception in the codebase, including internal ones never shown to users.

### Union syntax — Python 3.11+ style

Use `X | None` and `X | Y` union syntax. Never `Optional[X]` or `Union[X, Y]`. Ruff UP007 enforces this, but agents should write it correctly from the start.

### What ruff auto-fixes — don't internalize these

Import ordering (I001) and many formatting rules are auto-corrected by `uv run ruff check --fix . && uv run ruff format .`. Don't spend effort memorizing these — pre-commit handles them. Focus attention on rules that require semantic understanding (above).

---

## Framework-Specific Patterns

### Click CLI

All business logic lives in service classes, not in `@command` functions. CLI functions are thin wrappers: parse args, call service, print result. No logic in `cli.py`. Use `@group.command()` to add to existing groups — the top-level `cli` group and all subgroups (`search`, `ingest`, `daemon`, `govern`, `review`, `hooks`, `trigger`) are already defined in `cli.py`. Never create a parallel top-level command. Don't write unit tests for CLI functions — test the underlying service class instead.

### APScheduler

Scheduler: `BackgroundScheduler` with `ThreadPoolExecutor(max_workers=2)`. The `max_workers=2` limit is intentional and load-bearing — do not raise it without first fixing the index write mutex (P0-2). Job classes implement `execute() -> dict`; the returned dict is stored in `state/jobs.json` as `last_result`. New jobs go in `daemon/jobs/{name}.py` and must be imported and registered in `WikiDaemon.start()` via `self.scheduler.add_job(...)`. Jobs share no state between runs — they reload indexes from disk on each execution.

### FAISS

Use `faiss.write_index` / `faiss.read_index` for `IndexFlatL2` (float indexes). `write_index_binary` / `read_index_binary` are for `IndexBinaryFlat` only — using the wrong pair causes silent corruption or load failures at runtime. The vector index is `IndexFlatL2`, float32, 384 dimensions (all-MiniLM-L6-v2). Never change the dimension without rebuilding all stored vectors from scratch.

FAISS is an optional dependency (`uv sync --extra vector`). All FAISS imports are guarded: if imports fail, `add_document` and `rebuild_from_pages` log a warning and return 0; `search` returns `[]`. Never let a FAISS `ImportError` propagate to the caller.

### watchdog / inbox watcher

The inbox watcher moves files `inbox/new/` → `inbox/processing/` before ingesting. If the daemon crashes mid-ingest, files are orphaned in `inbox/processing/` with no automatic recovery (known P0-3). Don't write logic that assumes `inbox/processing/` is always clean on startup.

### python-frontmatter

Use `frontmatter.load(path)` to read; `frontmatter.dump(post, path)` or `frontmatter.dumps(post)` to serialize. `post.metadata` is the frontmatter dict; `post.content` is the markdown body. Never construct frontmatter manually as a raw string — always roundtrip through the library to preserve field ordering and YAML quoting.

---

## Testing Rules

### Core fixtures — use these, don't rebuild manually

Two fixtures cover almost all tests: `temp_dir: Path` (isolated temp directory per test) and `wiki_root: Path` (fully initialized `wiki_system/` structure in temp space). Use `wiki_root` for any test that reads or writes wiki files — never construct the directory structure by hand in a test. Both are defined in `tests/conftest.py`; shared fixtures belong there, module-local fixtures stay in the test file.

### Optional dependency guards

Tests requiring FAISS or sentence-transformers must use `pytest.importorskip("faiss")` or `pytest.importorskip("sentence_transformers")` at the top of the test (or in a fixture). Also mark them `@pytest.mark.slow`. Without the skip guard, the suite fails for users who haven't run `uv sync --extra vector`. The `-m "not slow"` flag skips these in fast local runs; CI runs the full suite.

### What to test — and what not to

- Test service classes and index classes directly. Never test CLI wrapper functions — test the service they delegate to.
- One test file per source module: `tests/unit/test_{module_name}.py`. End-to-end pipeline tests go in `tests/integration/`.
- Don't mock the filesystem — use `wiki_root` / `temp_dir` with real files. The architecture is file-based; a mocked fs loses the fidelity that matters.
- Don't mock index classes when testing the ingestion pipeline — use real instances pointed at temp dirs.

### LLM calls in tests

Patch `LLMClient.complete` to return a canned JSON response in unit tests — never make real API calls. Integration tests that exercise the full pipeline may use a real LLM if `OPENAI_API_KEY` is set, but must be marked `@pytest.mark.integration` and skipped otherwise.

### Test naming

`test_{behavior}` — describe what the code does, not which method is called. `test_search_returns_empty_on_missing_index` not `test_search_method`.

---

## Critical Anti-Patterns

### Atomic writes — the only safe index save pattern

All index `save()` methods must write atomically: write to a temp file, then `os.replace(tmp, target)`. `os.replace` is atomic on POSIX — the file either fully exists or doesn't. Direct `open(path, 'w')` writes leave a partially-written file if the process crashes mid-write, permanently corrupting the index. Reference implementation: `JobExecutionStore._save()`. All other current index saves are P0 bugs awaiting fix — don't add new non-atomic saves.

```python
import tempfile, os
with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False, suffix='.tmp') as f:
    json.dump(data, f, indent=2)
    tmp = f.name
os.replace(tmp, path)
```

### RRF sort key — the mypy overload trap

The Reciprocal Rank Fusion merge in `WikiQuery.search()` sorts by RRF score dict. The sort key must be a lambda, not `dict.get`:

```python
# WRONG — mypy overload resolution fails on dict.get as a key= argument
sorted(page_ids, key=rrf_scores.get, reverse=True)

# CORRECT
sorted(page_ids, key=lambda k: rrf_scores[k], reverse=True)
```

`dict.get` has two overloads (with/without default); mypy can't resolve which applies when passed as `key=`. The resulting type error is cryptic and silent. Always use the lambda form.

### FAISS API mismatch — silent corruption

`IndexFlatL2` (float) → `faiss.write_index` / `faiss.read_index`. `IndexBinaryFlat` → `faiss.write_index_binary` / `faiss.read_index_binary`. Mixing these produces a silent load failure or segfault, not a Python exception. This codebase uses `IndexFlatL2` exclusively.

### Page ID format — never construct manually

Page IDs are deterministic slugs: `{domain}-{title-slug}` (e.g., `general-python-typing`). They are the primary key across all 5 indexes, all frontmatter, and all backlink/graph edges. Always use `generate_page_id(domain, title)` from `models/page.py`. Never construct the slug by hand — slug normalization rules must stay consistent.

### Concurrent index writes — no mutex exists yet

The daemon runs up to 2 jobs concurrently via `ThreadPoolExecutor`. There is no write mutex on index files (P0-2). Any new job that writes to shared index files will race with `IndexRebuildJob`. Until the mutex lands, new jobs must not write to index files mid-run — either read-only, or scheduled to avoid overlap.

---

## Data Model & Storage Rules

### Page kinds — always use the factory

`PageFrontmatter` is the base class. Subtypes: `EntityFrontmatter` (kind: `entity`), `ConceptFrontmatter` (kind: `concept`), `SourceFrontmatter` (kind: `source`), `QAFrontmatter` (kind: `qa`). Always use `create_frontmatter(kind=..., ...)` from `models/page.py`. Never instantiate `PageFrontmatter` directly for a typed kind — bypassing the factory produces a page missing kind-specific fields (e.g., no `entity_type` on an entity page), which silently corrupts kind-based index filtering downstream with no immediate error.

Never add kind-specific fields to `PageFrontmatter` (the base class) — this pollutes all kinds and breaks `by_kind` filtering across governance and duplicate detection jobs.

### WikiQuery owns all index access

`WikiQuery` is the single point of entry for index reads and writes during normal operation. Jobs use `WikiQuery` methods (`add_page`, `remove_page`, `rebuild_indexes`) — they don't instantiate `FulltextIndex`, `VectorIndex`, etc. directly. The reason: concurrent direct saves from multiple jobs produce inconsistent index state (e.g., fulltext updated, vector not) with no exception raised. Only `IndexRebuildJob` instantiates index classes directly, as it is explicitly responsible for full rebuilds.

### Enumerating pages — filesystem, not indexes

To find which pages exist in a domain, scan `domains/{domain}/pages/*.md` on the filesystem. Never query `metadata.json` or any other index for this. Indexes are caches that may be up to 30 minutes stale; treating them as authoritative will silently skip recently-written pages that haven't been reindexed yet, or include pages that have been deleted.

### Index files are derived — never the source of truth

All 5 index files (`fulltext.json`, `vector_index.faiss`, `vector_meta.json`, `metadata.json`, `backlinks.json`, `graph_edges.json`) are derived from markdown page files. If stale or corrupt, run `trigger index-rebuild`. Never write logic that makes page lifecycle decisions (create, delete, update) based on index contents.

### State files are authoritative

`state/jobs.json` (written by `JobExecutionStore`) is the authoritative job execution record. It uses the only existing atomic write pattern in the codebase. Don't write job state by any other mechanism.

### Review queue — always use the service API

Review queue items have a lifecycle managed by the `ReviewQueue` service class. Never read, write, move, or delete files under `review_queue/` directly — status transitions (pending → approved/rejected/deferred) move files between subdirectories and update internal state counters. Bypassing the service breaks the queue's state with no error raised.

### Changelog — JSONL, append only

`wiki_system/logs/changelog.jsonl` is one JSON object per line. Append only — opening the file for write or rewriting it destroys the audit trail permanently and is unrecoverable. Parse with `json.loads(line)` per line, not `json.load(file)`. Write with `f.write(json.dumps(entry) + "\n")`.

### File path conventions

| Content | Path |
|---|---|
| Published page | `wiki_system/domains/{domain}/pages/{page_id}.md` |
| Queued page | `wiki_system/domains/{domain}/queue/{page_id}.md` |
| Cross-domain page | `wiki_system/shared/{page_id}.md` |
| Governance report | `wiki_system/reports/governance_{ts}.md` |
| Review item | `wiki_system/review_queue/{status}/{id}.json` |
| Changelog | `wiki_system/logs/changelog.jsonl` |
| Job state | `wiki_system/state/jobs.json` |

---

## Development Workflow Rules

### CI gates — run these locally before pushing

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest
```

CI runs this on Python 3.11 and 3.12. All four must pass. Pre-commit hooks run the same checks — install with `pre-commit install`. Never bypass with `--no-verify`; fix the underlying issue instead.

### Adding a new scheduled job

1. Create `daemon/jobs/{name}.py` — class with `execute() -> dict`
2. Import in `daemon/main.py`
3. Register in `WikiDaemon.start()` via `self.scheduler.add_job(...)`
4. Add config field to `DaemonConfig` in `models/config.py` if the job needs configuration
5. Write `tests/unit/test_{name}.py`

### Adding a new CLI command

Add to an existing group in `cli.py` via `@group.command()`. Delegate all logic to a service class. Test the service class, not the CLI wrapper.

### Adding a new index

Follow the `FulltextIndex` pattern: `save()` / `load()` / `rebuild_from_pages()` / `add_document()` / `remove_document()` / `search()`. Use atomic writes (tmp → `os.replace`). Integrate into `WikiQuery.search()`, `WikiQuery.add_page()`, `WikiQuery.remove_page()`, and `IndexRebuildJob.execute()`. Write unit tests using `wiki_root` fixture.

### Adding a new extraction step

Create `extraction/{name}.py` with a class implementing `extract(content: str) -> ExtractorResult`. Register in `EnrichmentPipeline` (`extraction/enrichment.py`). Add the result schema to `PageFrontmatter` in `models/page.py`. Write unit tests with mocked `LLMClient`.

### Ruff and target version config

Line length: 100 (not 79 or 88). Target: `py311`. Write Python 3.11+ syntax — union types (`X | Y`), `match` statements, `tomllib`. Configured in `pyproject.toml`; don't override per-file.

### Dependency management

Add with `uv add {package}`. Optional extras: `uv add --optional {extra} {package}`. Never edit `uv.lock` manually. Never use `pip install`. Check `pyproject.toml` first — the dependency may already be listed.
