# LLM Wiki - GitHub Copilot Instructions

GitHub Copilot integration for the federated wiki system.

## System Overview

This is a knowledge management system with domain-specific wikis. The wiki stores content in `wiki_system/domains/` and supports fulltext search, governance, and LLM-optimized exports.

## Project Structure

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
├── exports/           # Generated exports (llms.txt, graph.json)
├── reports/           # Governance reports
├── logs/              # Daemon logs
└── state/             # System state
```

## Available Domains

- **vulpine-solutions**: MSP, operations, sales, security, client delivery
- **home-assistant**: Automation, voice assistant, ESP32, local AI, sensors
- **homelab**: Proxmox, k3s, storage, networking, GPUs, services
- **personal**: Family logistics, hobbies, plans, notes
- **general**: Fallback bucket for unclassified or low-confidence content

## Quick Reference

### Querying the Wiki

Use the Python API:

```python
from llm_wiki.query.search import WikiQuery
from pathlib import Path

wiki = WikiQuery(wiki_base=Path("wiki_system"))
results = wiki.search("python programming", domain="vulpine-solutions")
# Returns: [{"id": "...", "title": "...", "domain": "...", "summary": "...", "score": ...}]
```

### Adding Content

Drop markdown files in `wiki_system/inbox/` with frontmatter:

```yaml
---
id: my-page-id
title: My Page Title
domain: general
tags:
  - tag1
  - tag2
summary: Brief description of the page.
---
```

Or use CLI:
```bash
uv run llm-wiki ingest file /path/to/file.md --domain general
```

### Running Governance

```bash
uv run llm-wiki govern check
```

### Exporting

```bash
uv run llm-wiki export all
uv run llm-wiki export llmstxt
```

## Page Format

### Required Frontmatter

```yaml
---
id: page-id              # Unique identifier (kebab-case)
title: Page Title        # Human-readable title
domain: domain-name      # Domain from config/domains.yaml
---
```

### Recommended Fields

```yaml
kind: page               # page, entity, concept, source
summary: Brief description
tags:
  - tag1
  - tag2
source: https://...      # Citation/source URL
created: 2024-01-01T00:00:00Z
updated: 2024-01-01T00:00:00Z
```

### Linking

Link to pages using: `[[page-id]]`

Example: See [[python-programming]] for details.

## Configuration

- **domains**: `config/domains.yaml`
- **routing**: `config/routing.yaml`
- **models**: `config/models.yaml`
- **daemon**: `config/daemon.yaml`

## CLI Commands

```bash
# Initialize wiki
uv run llm-wiki init

# Search
uv run llm-wiki search query "query"
uv run llm-wiki search get page-id

# Ingest
uv run llm-wiki ingest file path.md --domain domain
uv run llm-wiki ingest text "content" --domain domain

# Governance
uv run llm-wiki govern check
uv run llm-wiki govern rebuild-index

# Export
uv run llm-wiki export all
uv run llm-wiki export llmstxt
uv run llm-wiki export graph

# Daemon
uv run llm-wiki daemon
```

## Development

- Run tests: `uv run pytest`
- Run daemon: `uv run llm-wiki daemon`
- Rebuild indexes: `uv run llm-wiki govern rebuild-index`

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture
- [docs/SETUP.md](docs/SETUP.md) - Setup guide
- [docs/AGENT_CONVENTIONS.md](docs/AGENT_CONVENTIONS.md) - Cross-agent conventions
- [docs/AGENT_SUPPORT_MATRIX.md](docs/AGENT_SUPPORT_MATRIX.md) - Integration status