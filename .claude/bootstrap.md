# LLM Wiki Agent Bootstrap

This is a federated wiki system for agent knowledge management.

## Quick Start

Use these slash commands:
- `/wiki <query>` - Search wiki pages
- `/ingest <file>` - Add content to wiki
- `/export` - Generate exports (llms.txt, graph, etc.)
- `/govern` - Run governance checks

## System Structure

```
wiki_system/
├── domains/           # Domain-specific wikis
│   ├── general/
│   ├── tech/
│   ├── homelab/
│   └── .../
├── inbox/             # Drop files here for ingestion
├── index/             # Search indexes
├── exports/           # Generated exports
└── reports/           # Governance reports
```

## Domain Overview

Active domains (check `config/domains.yaml` for full list):
- **general**: Default domain for uncategorized content
- **tech**: Technology, programming, tools
- **homelab**: Infrastructure, self-hosting
- **personal**: Personal notes and tasks

## Page Kinds

- **page**: Standard wiki page
- **entity**: People, organizations, technologies, tools
- **concept**: Ideas, methodologies, patterns
- **source**: Source documents

## Linking Conventions

Link to other pages using: `[[page-id]]`

Page IDs are kebab-case (e.g., `python-programming`, `api-design`)

## Recent Changes

Check latest governance report:
```bash
ls -lt wiki_system/reports/ | head -5
```

Check latest exports:
```bash
ls -lt wiki_system/exports/
```

## Common Tasks

### Query wiki
```python
from llm_wiki.query.search import WikiQuery

wiki = WikiQuery()
results = wiki.search("python", domain="tech", kind="entity")
```

### Add content
Drop files in `wiki_system/inbox/` - they'll be auto-processed.

### Check quality
```python
from llm_wiki.daemon.jobs.governance import run_governance_check

stats = run_governance_check()
print(f"Lint issues: {stats['lint_issues']}")
print(f"Stale pages: {stats['stale_pages']}")
```

### Export for LLMs
```python
from llm_wiki.export.llmstxt import LLMSTxtExporter

exporter = LLMSTxtExporter()
path = exporter.export_all()
print(f"Exported to: {path}")
```

## Configuration

- **domains**: `config/domains.yaml`
- **routing**: `config/routing.yaml`
- **models**: `config/models.yaml`
- **daemon**: `config/daemon.yaml`

## Development

Run tests: `uv run pytest`
Run daemon: `uv run llm-wiki daemon start`
Rebuild indexes: `uv run python -m llm_wiki.daemon.jobs.index_rebuild`

## Help

- See `/docs/IMPLEMENTATION_STATUS.md` for feature status
- See `/docs/roadmap.md` for planned features
- Create issues at https://github.com/marcmontecalvo/llm_wiki/issues
