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
│   ├── vulpine-solutions/
│   ├── home-assistant/
│   ├── homelab/
│   ├── personal/
│   └── general/
├── inbox/             # Drop files here for ingestion
├── index/             # Search indexes
├── exports/           # Generated exports
├── reports/           # Governance reports
├── logs/              # Daemon logs
└── state/             # System state
```

## Domain Overview

Active domains (check `config/domains.yaml` for full list):
- **vulpine-solutions**: MSP, operations, sales, security, client delivery
- **home-assistant**: Automation, voice assistant, ESP32, local AI, sensors
- **homelab**: Proxmox, k3s, storage, networking, GPUs, services
- **personal**: Family logistics, hobbies, plans, notes
- **general**: Fallback bucket for unclassified or low-confidence content

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
from pathlib import Path

wiki = WikiQuery(wiki_base=Path("wiki_system"))
results = wiki.search("python", domain="vulpine-solutions", kind="entity")
```

### Add content
Drop files in `wiki_system/inbox/` - they'll be auto-processed.

### Check quality
```python
from llm_wiki.daemon.jobs.governance import GovernanceJob
from pathlib import Path

job = GovernanceJob(wiki_base=Path("wiki_system"))
stats = job.execute()
print(f"Lint issues: {stats['lint_issues']}")
print(f"Stale pages: {stats['stale_pages']}")
```

### Export for LLMs
```python
from llm_wiki.export.llmstxt import LLMSTxtExporter
from pathlib import Path

exporter = LLMSTxtExporter(wiki_base=Path("wiki_system"))
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
Run daemon: `uv run llm-wiki daemon`
Rebuild indexes: `uv run llm-wiki govern rebuild-index`

## Help

- See `docs/IMPLEMENTATION_STATUS.md` for feature status
- See `docs/ARCHITECTURE.md` for system architecture
- See `docs/AGENT_CONVENTIONS.md` for agent integration
- Create issues at https://github.com/marcmontecalvo/llm_wiki/issues
