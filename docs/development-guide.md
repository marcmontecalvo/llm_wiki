# LLM Wiki — Development Guide

## Prerequisites

- **Python 3.11+** (3.12 also tested in CI)
- **uv** — project package manager (`brew install uv` or `curl -Ls https://astral.sh/uv/install.sh | sh`)
- **git**

> **Important**: Never use `python3` or `pip` directly — always use `uv run python` and `uv add`. The system Python on macOS is often 3.10 or older.

## Setup

```bash
# Clone and enter the repo
git clone <repo-url>
cd llm_wiki

# Install all dependencies (reads pyproject.toml + uv.lock)
uv sync

# Verify installation
uv run llm-wiki --help
uv run pytest --version
```

### Optional: Vector Search Dependencies

```bash
# Adds faiss-cpu + sentence-transformers (~500MB download including model)
uv sync --extra vector

# Or add to your local install
uv add --optional vector faiss-cpu sentence-transformers
```

### Optional: Claude Agent SDK

```bash
uv sync --extra claude-agent
```

## Initialize a Wiki Instance

```bash
# Creates wiki_system/ directory structure and default config/ YAML files
uv run llm-wiki init

# Review and edit generated configs
cat config/domains.yaml    # Domain definitions
cat config/daemon.yaml     # Scheduling intervals
cat config/models.yaml     # LLM provider settings
cat config/routing.yaml    # Source → domain routing rules
```

## Running Tests

```bash
# All tests (1,106 passing)
uv run pytest

# With coverage report
uv run pytest --cov=src/llm_wiki --cov-report=term-missing

# Single module
uv run pytest tests/unit/test_vector_index.py -v

# Skip slow tests (vector index tests that download model)
uv run pytest -m "not slow"

# Integration tests only
uv run pytest tests/integration/ -v
```

### Test Organization

```
tests/
├── conftest.py          # Shared fixtures
│   ├── temp_dir         # pytest tmp_path wrapped for convenience
│   └── wiki_root        # Initialized wiki_system/ in temp space
├── unit/                # One test file per source module
└── integration/         # Full pipeline end-to-end tests
```

**Key fixtures** (`conftest.py`):
- `temp_dir: Path` — isolated temporary directory per test
- `wiki_root: Path` — initialized `wiki_system/` structure in temp space

## Linting and Type Checking

```bash
# Ruff lint (must pass — 0 errors)
uv run ruff check .

# Ruff format check
uv run ruff format --check .

# Auto-fix lint issues
uv run ruff check --fix .
uv run ruff format .

# mypy type check (must pass — 0 new errors)
uv run mypy src/

# Run all CI checks locally
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest
```

**Ruff config** (in `pyproject.toml`):
- Line length: 100
- Target: Python 3.11
- Rules include: E, W, F, B (flake8-bugbear), N818 (exception names must end in `Error`), I001 (import sorting)

**mypy config** (in `pyproject.toml`):
- `disallow_untyped_defs = false` — partial typing is acceptable
- `warn_return_any = true`
- Expected: `import-untyped` warnings for third-party libs without stubs (faiss, sentence-transformers, apscheduler)

## Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

Hooks run: ruff check, ruff format, mypy. Same checks as CI.

## Running the Daemon

```bash
# Start daemon (foreground, Ctrl-C to stop)
uv run llm-wiki daemon start

# Check daemon status
uv run llm-wiki daemon status

# List registered jobs and their next run times
uv run llm-wiki daemon jobs

# Trigger a specific job manually
uv run llm-wiki trigger index-rebuild
uv run llm-wiki trigger governance-check
```

## Ingesting Content

```bash
# Ingest a markdown file
uv run llm-wiki ingest file path/to/document.md

# Ingest plain text
uv run llm-wiki ingest text "This is a note about X" --domain general

# Ingest an Obsidian vault
uv run llm-wiki ingest obsidian /path/to/vault/

# Check ingestion stats
uv run llm-wiki ingest stats

# List failed ingestions
uv run llm-wiki ingest failed
```

## Searching

```bash
# Fulltext + vector search (RRF fusion)
uv run llm-wiki search query "how does X work"

# Filter by domain
uv run llm-wiki search query "kubernetes" --domain homelab

# Get a specific page by ID
uv run llm-wiki search get <page-id>

# Find pages that link to a page
uv run llm-wiki search backlinks <page-id>
```

## Session Capture Hooks (Claude Code)

The project includes hooks that automatically capture Claude Code sessions into the wiki.

```bash
# Install hooks for the current project
uv run llm-wiki hooks install --scope project

# Install globally for all projects
uv run llm-wiki hooks install --scope user

# Uninstall
uv run llm-wiki hooks uninstall
```

Hooks:
- `SessionEnd` — captures full session transcript at end of conversation
- `PreCompact` — captures session before context compaction

## Development Workflow

### Adding a New Scheduled Job

1. Create `src/llm_wiki/daemon/jobs/{job_name}.py` with a class implementing `execute() -> dict`
2. Import in `src/llm_wiki/daemon/main.py`
3. Register in `WikiDaemon.start()` with `self.scheduler.add_job(...)`
4. Add job name to `DaemonConfig` if it needs configuration
5. Write unit tests in `tests/unit/test_{job_name}.py`

### Adding a New CLI Command

1. Find the appropriate command group in `src/llm_wiki/cli.py` (or create a new group)
2. Add a `@group.command()` decorated function
3. Keep business logic out of cli.py — delegate to a service class
4. Write tests for the underlying service, not the CLI wrapper

### Adding a New Index

1. Create `src/llm_wiki/index/{name}.py` following the `FulltextIndex` pattern (save/load/rebuild/add_document/remove_document/search)
2. Use atomic writes: `tmp → os.replace()` (see `JobExecutionStore._save()` for the pattern)
3. Integrate into `WikiQuery.search()` if it participates in search
4. Add rebuild logic to `IndexRebuildJob.execute()`
5. Write unit tests

### Extending the Extraction Pipeline

1. Create `src/llm_wiki/extraction/{extractor_name}.py` with a class implementing `extract(content: str) -> ExtractorResult`
2. Register in `EnrichmentPipeline` in `extraction/enrichment.py`
3. Add the result schema to `models/page.py` frontmatter
4. Add the result field to the Pydantic `PageFrontmatter` schema

## Project Configuration

### LLM Provider Configuration

Edit `config/models.yaml`:

```yaml
extraction:
  provider: openai          # or: anthropic, ollama, lm_studio, claude_agent_sdk
  model: gpt-4o-mini
  temperature: 0.1
  max_tokens: 2000
  timeout: 30               # seconds

integration:
  provider: openai
  model: gpt-4o
  temperature: 0.0
  max_tokens: 4000
  timeout: 60
```

Supported providers all use OpenAI-compatible API endpoints. For Anthropic: set `base_url` to the Anthropic compatibility endpoint. For Ollama: `base_url: http://localhost:11434/v1`.

### Domain Configuration

Edit `config/domains.yaml`:

```yaml
domains:
  - id: my-domain           # lowercase-hyphenated, used in all paths
    title: My Domain
    description: What goes here
    owners: [me]
    promote_to_shared: true  # whether pages can be promoted to shared/
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`):

```
push/PR to main
  └── test job (matrix: Python 3.11, 3.12)
      ├── uv sync
      ├── ruff check .
      ├── ruff format --check .
      ├── mypy src/
      ├── pytest --cov --cov-report=xml
      └── codecov upload
  └── build job (requires test to pass)
      └── uv build
```

All PRs must pass both jobs before merging.

## Troubleshooting

### "Python 3.11+ is required"
Use `uv run python` instead of `python3`. System Python on macOS may be 3.10.

### FAISS SWIG deprecation warnings
Harmless. Expected output from `faiss-cpu` — will be fixed in a future faiss release.

### `sign_and_send_pubkey: signing failed`
SSH agent issue (often 1Password SSH agent). Restart the agent or push in a new terminal session.

### Index seems stale or empty
Run `uv run llm-wiki trigger index-rebuild` to force a full rebuild.

### Daemon won't start — config validation error
Check `config/daemon.yaml`, `config/domains.yaml`, `config/models.yaml`, `config/routing.yaml`. Run `uv run llm-wiki daemon start` and read the error message — it will name the specific invalid field.
