# LLM Wiki Setup Guide

Complete setup instructions for the LLM wiki system.

## Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/marcmontecalvo/llm_wiki.git
cd llm_wiki
```

### 2. Install Dependencies

Using uv (recommended):
```bash
uv sync
```

Using pip:
```bash
pip install -e .
```

### 3. Initialize Wiki Structure

```bash
# Use the CLI to create wiki_system/ with all required directories
uv run llm-wiki init
```

This creates the wiki structure based on your `config/domains.yaml`.

### 4. Configure Domains

Edit `config/domains.yaml` to define your domains:

```yaml
domains:
  - id: vulpine-solutions
    title: Vulpine Solutions
    description: MSP, operations, sales, security, client delivery
    owners: [user]
    promote_to_shared: true

  - id: general
    title: General
    description: Fallback bucket for unclassified content
    owners: [system]
    promote_to_shared: false

  # Add your custom domains here
```

### 5. Configure Models

Edit `config/models.yaml` with your LLM provider settings:

```yaml
default_provider: openai

providers:
  openai:
    api_key: ${OPENAI_API_KEY}
    base_url: https://api.openai.com/v1
    model: gpt-4
```

Set your API key:
```bash
export OPENAI_API_KEY=your-key-here
```

**Alternative: use Claude subscription instead of metered API.**

If you're on Claude Max/Team/Enterprise, route extraction through the
Claude Agent SDK (no API key needed):

```bash
uv sync --extra claude-agent
```

```yaml
# config/models.yaml
extraction:
  provider: claude_agent_sdk
  model: claude-sonnet-4-5
```

### 6. (Optional) Install Claude Code Hooks

Automatically capture Claude Code sessions into the inbox:

```bash
uv run llm-wiki hooks install --scope project
```

This writes `SessionEnd` and `PreCompact` entries into
`.claude/settings.json`. Every session transcript lands in
`wiki_system/inbox/new/session-*.jsonl` and the daemon picks it up.
Use `--scope user` to apply the hooks globally across all projects.

Preview without writing: `--dry-run`. Remove later:
`uv run llm-wiki hooks uninstall`.

## Quick Start

### Add Content

Drop a file in the inbox:
```bash
echo "# Python Programming

Python is a high-level programming language." > wiki_system/inbox/python.md
```

Or use the ingest skill:
```bash
# From Claude Code
/ingest my-notes.md --domain tech
```

### Query Wiki

Using CLI:
```bash
uv run llm-wiki search query "python"
```

Using Python:
```python
from llm_wiki.query.search import WikiQuery
from pathlib import Path

wiki = WikiQuery(wiki_base=Path("wiki_system"))
results = wiki.search("python")

for r in results:
    print(f"{r['title']} ({r['domain']})")
```

Using the skill:
```bash
/wiki python --domain tech
```

### Run Governance

Check wiki quality using CLI:
```bash
uv run llm-wiki govern check
```

Or use the skill:
```bash
/govern
```

Using Python:
```python
from llm_wiki.daemon.jobs.governance import GovernanceJob
from pathlib import Path

job = GovernanceJob(wiki_base=Path("wiki_system"))
stats = job.execute()
print(f'Lint issues: {stats["lint_issues"]}')
print(f'Stale pages: {stats["stale_pages"]}')
```

### Export Content

Generate exports using CLI:
```bash
# Export all formats
uv run llm-wiki export all

# Export specific format
uv run llm-wiki export llmstxt
uv run llm-wiki export graph
```

Or use the skill:
```bash
/export
```

Using Python:
```python
from llm_wiki.daemon.jobs.export import ExportJob
from pathlib import Path

job = ExportJob(wiki_base=Path("wiki_system"))
stats = job.execute()
print(f'Exported to: {stats["llmstxt_path"]}')
```

## Configuration

### Domain Routing

Edit `config/routing.yaml` to configure auto-routing:

```yaml
routing_rules:
  - pattern: "*/tech/*"
    domain: tech
    confidence: 0.9

  - pattern: "*/homelab/*"
    domain: homelab
    confidence: 0.9

# Add your custom routing rules
```

### Daemon Settings

Edit `config/daemon.yaml` for daemon configuration:

```yaml
daemon:
  check_interval: 60  # seconds
  max_concurrent_jobs: 3
  log_level: INFO

jobs:
  inbox_watcher:
    enabled: true
    interval: 30

  index_rebuild:
    enabled: true
    interval: 3600

  governance:
    enabled: true
    interval: 7200

  export:
    enabled: true
    interval: 3600
```

## Development

### Run Tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=src/llm_wiki

# Specific test file
uv run pytest tests/unit/test_query.py

# Watch mode
uv run pytest-watch
```

### Code Quality

```bash
# Run linters
uv run ruff check .
uv run ruff format .
uv run mypy src/

# Fix auto-fixable issues
uv run ruff check --fix .
```

### Pre-commit Hooks

Install pre-commit hooks:
```bash
pre-commit install
```

Hooks will run automatically on commit.

## Troubleshooting

### Issue: Import errors

**Solution**: Ensure you've installed in editable mode:
```bash
uv pip install -e .
```

### Issue: API key not found

**Solution**: Set environment variable:
```bash
export OPENAI_API_KEY=your-key
# Or add to .env file
```

### Issue: Permission errors on wiki_system

**Solution**: Check directory permissions:
```bash
chmod -R u+w wiki_system/
```

### Issue: Tests failing

**Solution**: Rebuild test fixtures:
```bash
uv run pytest --cache-clear
```

### Issue: Stale indexes

**Solution**: Rebuild indexes using CLI:
```bash
uv run llm-wiki govern rebuild-index
```

Or using Python:
```python
from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob
from pathlib import Path

job = IndexRebuildJob(wiki_base=Path("wiki_system"))
job.execute()
```

## Agent Integration

### Claude Code

Skills are in `.claude/skills/`:
- `/wiki` - Query wiki
- `/ingest` - Add content
- `/export` - Generate exports
- `/govern` - Run checks

See `.claude/bootstrap.md` for full agent guide.

### Other Agents

Use the Python API directly:
```python
from llm_wiki.query.search import WikiQuery
from llm_wiki.export.llmstxt import LLMSTxtExporter
from pathlib import Path

wiki_base = Path("wiki_system")

# Query
wiki = WikiQuery(wiki_base=wiki_base)
results = wiki.search("topic")

# Export for agent context
exporter = LLMSTxtExporter(wiki_base=wiki_base)
llmstxt_path = exporter.export_all()
```

## Next Steps

- Read [Architecture](ARCHITECTURE.md) for system design
- See [Agent Conventions](AGENT_CONVENTIONS.md) for usage guidelines
- Check [Implementation Status](IMPLEMENTATION_STATUS.md) for features
- Browse [Examples](../examples/) for workflows

## Support

- Issues: https://github.com/marcmontecalvo/llm_wiki/issues
- Docs: `/docs/` directory
- Tests: `/tests/` for usage examples
