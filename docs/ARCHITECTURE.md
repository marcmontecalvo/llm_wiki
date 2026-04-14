# LLM Wiki Architecture

System architecture and design overview.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         LLM Wiki System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐ │
│  │  Ingest  │───▶│ Extraction│───▶│   Index  │───▶│  Export  │ │
│  └──────────┘    └───────────┘    └──────────┘    └──────────┘ │
│       │               │                 │               │        │
│       ▼               ▼                 ▼               ▼        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Federated Wiki Storage                      │  │
│  │  (domains configured in config/domains.yaml)             │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         Governance Layer (Lint, Quality, Staleness)      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Ingest Pipeline

**Purpose**: Normalize diverse inputs into standard wiki format.

**Components**:
- **Inbox Watcher**: Monitors `wiki_system/inbox/` for new files
- **Source Adapters**: Convert inputs to markdown
  - `MarkdownAdapter`: Process .md files
  - `TextAdapter`: Process .txt files
- **Domain Router**: Assign content to appropriate domain
- **Normalizer**: Create standard frontmatter

**Flow**:
```
inbox/ → adapter → router → normalize → domains/{domain}/queue/
```

**Key Files**:
- `src/llm_wiki/ingest/watcher.py`
- `src/llm_wiki/adapters/*.py`
- `src/llm_wiki/ingest/router.py`

### 2. Extraction Pipeline

**Purpose**: Extract structured metadata from content.

**Components**:
- **Content Extractor**: Extract basic metadata (title, tags, kind)
- **Entity Extractor**: Identify entities (people, tech, tools)
- **Concept Extractor**: Identify concepts (ideas, methodologies)
- **Page Enricher**: Merge extracted data into pages

**Flow**:
```
queue/ → extract metadata → extract entities/concepts → enrich → pages/
```

**Key Files**:
- `src/llm_wiki/extraction/service.py`
- `src/llm_wiki/extraction/entities.py`
- `src/llm_wiki/extraction/concepts.py`
- `src/llm_wiki/extraction/enrichment.py`

### 3. Index System

**Purpose**: Enable fast searching and querying.

**Components**:
- **Metadata Index**: Tag, kind, domain lookups
- **Fulltext Index**: TF-IDF search with inverted index
- **Query Interface**: Unified search API

**Data Structures**:
```python
# Metadata Index
{
  "pages": {"page-id": {metadata}},
  "by_tag": {"python": {"page1", "page2"}},
  "by_kind": {"entity": {"page1"}},
  "by_domain": {"tech": {"page1", "page2"}}
}

# Fulltext Index
{
  "inverted_index": {"word": {"page-id": count}},
  "documents": {"page-id": {metadata}}
}
```

**Key Files**:
- `src/llm_wiki/index/metadata.py`
- `src/llm_wiki/index/fulltext.py`
- `src/llm_wiki/query/search.py`

### 4. Governance System

**Purpose**: Maintain wiki quality and health.

**Components**:
- **Metadata Linter**: Validate frontmatter, check citations
- **Staleness Detector**: Find outdated content
- **Quality Scorer**: Multi-factor quality assessment
- **Governance Job**: Orchestrate checks, generate reports

**Checks**:
- Required fields present
- Valid field types
- Citation presence
- Page age and updates
- Content quality (length, structure)
- Orphan detection

**Key Files**:
- `src/llm_wiki/governance/linter.py`
- `src/llm_wiki/governance/staleness.py`
- `src/llm_wiki/governance/quality.py`
- `src/llm_wiki/daemon/jobs/governance.py`

### 5. Export System

**Purpose**: Generate machine-readable outputs.

**Formats**:
- **llms.txt**: LLM-optimized context files
- **JSON Sidecars**: Per-page metadata
- **Graph**: Nodes and edges representation
- **Sitemap**: XML sitemap for navigation

**Key Files**:
- `src/llm_wiki/export/llmstxt.py`
- `src/llm_wiki/export/json_sidecar.py`
- `src/llm_wiki/export/graph.py`
- `src/llm_wiki/export/sitemap.py`

## Data Flow

### Ingest to Active Page

```
1. File dropped in inbox/
2. Watcher detects new file
3. Adapter normalizes to markdown
4. Router assigns domain
5. File moved to domains/{domain}/queue/
6. Content extractor analyzes content
7. Entity/concept extractors run (if applicable)
8. Page enricher merges metadata
9. File moved to domains/{domain}/pages/
10. Indexes updated
```

### Search Query

```
1. Query submitted via WikiQuery
2. Fulltext index searched (if query text provided)
3. Metadata filters applied (domain, kind, tags)
4. Results scored and ranked
5. Top N results returned
```

### Export Generation

```
1. Export job triggered
2. All domains scanned
3. Each exporter generates output:
   - llms.txt: Concatenated markdown
   - JSON: Per-page metadata
   - Graph: Nodes + edges
   - Sitemap: XML file list
4. Files written to exports/
```

## Storage Layout

```
wiki_system/
├── inbox/              # Drop zone for new files
├── domains/            # Domain-specific wikis (configured in config/domains.yaml)
│   ├── vulpine-solutions/
│   │   ├── queue/      # Pending extraction
│   │   └── pages/      # Active wiki pages
│   ├── home-assistant/
│   │   ├── queue/
│   │   └── pages/
│   ├── homelab/
│   │   ├── queue/
│   │   └── pages/
│   ├── personal/
│   │   ├── queue/
│   │   └── pages/
│   └── general/
│       ├── queue/
│       └── pages/
├── index/              # Search indexes
│   ├── metadata.json
│   └── fulltext.json
├── exports/            # Generated exports
│   ├── llms.txt
│   ├── graph.json
│   └── sitemap.xml
├── reports/            # Governance reports
│   └── governance_*.md
├── logs/               # Daemon logs
└── state/              # System state
```

## Configuration

### Config Files

- `config/domains.yaml`: Domain definitions
- `config/routing.yaml`: Auto-routing rules
- `config/models.yaml`: LLM provider settings
- `config/daemon.yaml`: Daemon job schedules

### Pydantic Models

Strict schemas for all data structures:
- `models/domain.py`: Domain configuration
- `models/page.py`: Page frontmatter
- `models/extraction.py`: Extraction outputs
- `models/config.py`: Model provider config

## Design Principles

### 1. Local-First
- All operations work offline
- No required cloud dependencies
- Optional LLM for extraction

### 2. Federated Architecture
- Multiple domain-specific wikis
- Shared infrastructure
- Independent evolution

### 3. Deterministic Processing
- Same input → same output
- Re-runnable pipelines
- No silent rewrites

### 4. Structured Data
- Strict schemas (Pydantic)
- Validated at every step
- No loose dict soup

### 5. Append-Only Operations
- Preserve history (future)
- Change logs (future)
- Reversible operations

## Extension Points

### Adding Adapters

```python
from llm_wiki.adapters.base import BaseAdapter

class CustomAdapter(BaseAdapter):
    def can_parse(self, filepath: Path) -> bool:
        return filepath.suffix == ".custom"

    def extract_metadata(self, filepath: Path) -> dict:
        # Extract metadata
        return {"title": "...", ...}

    def normalize_to_markdown(self, filepath: Path, content: str) -> str:
        # Convert to markdown
        return "# Title\n\nContent..."
```

### Adding Extractors

```python
from typing import Any

class CustomExtractor:
    def extract(self, content: str, metadata: dict) -> list[dict[str, Any]]:
        # Extract custom data
        return [{"name": "...", "type": "..."}]
```

### Adding Exporters

```python
from pathlib import Path

class CustomExporter:
    def __init__(self, wiki_base: Path):
        self.wiki_base = wiki_base

    def export(self, output_file: Path) -> Path:
        # Generate custom export
        return output_file
```

## Performance Considerations

### Indexing
- Incremental updates supported
- Full rebuild available
- Indexes cached on disk

### Search
- TF-IDF scoring: O(n) where n = matching docs
- Metadata filtering: O(1) lookup via indexes
- Combined: Fast for typical queries

### Extraction
- Runs asynchronously in queue
- Batching possible (not implemented)
- LLM calls are bottleneck

## Security

### Input Validation
- All inputs validated against Pydantic schemas
- File paths sanitized
- No code execution from content

### API Keys
- Stored in environment variables
- Never committed to repo
- Provider-agnostic design

### Isolation
- Each domain isolated on filesystem
- No cross-domain writes
- Promotion requires explicit action

## Testing

### Unit Tests
- 523 tests, 93% coverage
- Comprehensive mocking
- Fast execution (<15s)

### Integration Tests
- End-to-end pipelines
- Real file I/O
- Slower but realistic

### Fixtures
- `temp_dir`: Isolated test directories
- Mock LLM clients
- Sample wiki structures

## Future Enhancements

See `IMPLEMENTATION_STATUS.md` for planned features:
- Enhanced daemon scheduler (#82)
- Contradiction detection (#70)
- Review queue (#71)
- Claims extraction (#66)
- Relationships extraction (#67)
- Backlink tracking (#69)
- Promotion logic (#68)
