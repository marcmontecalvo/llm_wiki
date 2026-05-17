# LLM Wiki — Data Models

All persistent data in LLM Wiki is stored as files: markdown with YAML frontmatter for wiki pages, JSON for indexes and state, and YAML for configuration. This document describes all data structures.

## Page Models

### Base: `PageFrontmatter`

Every wiki page is a markdown file with a YAML frontmatter block. The base schema:

```yaml
---
id: "general-python-typing"          # Deterministic slug: {domain}-{title-slug}
kind: "page"                          # page | entity | concept | source | qa
title: "Python Typing"
domain: "general"
status: "published"                   # draft | published | archived | review
confidence: 0.85                      # 0.0 - 1.0 (LLM extraction confidence)
sources: []                           # List of source page IDs or URLs
links: []                             # Links to other page IDs
updated_at: "2026-05-16T00:00:00Z"
created_at: "2026-05-16T00:00:00Z"
tags: ["python", "typing", "mypy"]
relationships: []                     # List of typed relationship dicts
---

Page content in markdown...
```

**Pydantic model**: `src/llm_wiki/models/page.py::PageFrontmatter`

### `EntityFrontmatter` (kind: "entity")

Represents a named entity (person, organization, product, tool):

```yaml
---
kind: "entity"
# ... base fields ...
entity_type: "tool"                   # person | org | product | tool | location | other
aliases: ["mypy", "mypy type checker"]
---
```

### `ConceptFrontmatter` (kind: "concept")

Represents an abstract concept or topic:

```yaml
---
kind: "concept"
# ... base fields ...
related_concepts: ["type-theory", "static-analysis"]
---
```

### `SourceFrontmatter` (kind: "source")

Represents an ingested source document:

```yaml
---
kind: "source"
# ... base fields ...
source_type: "markdown"               # markdown | text | obsidian | claude_session
source_path: "/path/to/original.md"
ingested_at: "2026-05-16T00:00:00Z"
adapter: "MarkdownAdapter"
---
```

### `QAFrontmatter` (kind: "qa")

Represents a question-answer pair extracted from content:

```yaml
---
kind: "qa"
# ... base fields ...
question: "What is the difference between X and Y?"
answer: "X does A while Y does B..."
related_pages: ["general-x-concept", "general-y-concept"]
---
```

### Factory Function

```python
from llm_wiki.models.page import create_frontmatter

fm = create_frontmatter(
    kind="entity",
    id="general-python",
    title="Python",
    domain="general",
    entity_type="tool",
)
```

## Configuration Models

All in `src/llm_wiki/models/config.py`, loaded from `config/*.yaml`.

### `WikiConfig` (top-level aggregate)

```python
class WikiConfig(BaseModel):
    domains: list[DomainConfig]
    daemon: DaemonConfig
    models: ModelsYAML          # extraction, integration, lint providers
    routing: RoutingYAML        # source path → domain rules
```

### `DomainConfig`

```python
class DomainConfig(BaseModel):
    id: str                      # lowercase-hyphenated
    title: str
    description: str
    owners: list[str]
    promote_to_shared: bool = False
```

Example (`config/domains.yaml`):
```yaml
domains:
  - id: vulpine-solutions
    title: Vulpine Solutions
    description: Work and consulting knowledge
    owners: [marc]
    promote_to_shared: true
```

### `DaemonConfig`

```python
class DaemonConfig(BaseModel):
    inbox_poll_seconds: int = 15
    migrate_queue_every_minutes: int = 15
    retry_failed_ingests_every_minutes: int = 30
    rebuild_index_every_minutes: int = 30
    lint_every_minutes: int = 60
    export_every_minutes: int = 60
    max_parallel_jobs: int = 2
    log_level: str = "INFO"
    review_queue_enabled: bool = True
```

### `ModelProviderConfig`

```python
class ModelProviderConfig(BaseModel):
    provider: str                # openai | anthropic | ollama | lm_studio | claude_agent_sdk
    model: str
    temperature: float = 0.1
    max_tokens: int | None = None
    timeout: int = 30            # seconds (not yet enforced — P0-4)
    base_url: str | None = None
    api_key_env: str | None = None
```

### `PromotionConfig`

```python
class PromotionConfig(BaseModel):
    auto_promote_threshold: float = 10.0
    suggest_promote_threshold: float = 5.0
    min_quality_score: float = 0.6
    min_cross_domain_refs: int = 2
    require_approval: bool = True
```

### `DuplicatesConfig`

```python
class DuplicatesConfig(BaseModel):
    min_score_to_flag: float = 0.5
    auto_merge_threshold: float = 0.9
```

## Index Storage Formats

### `fulltext.json` — TF-IDF Inverted Index

```json
{
  "index": {
    "python": {
      "general-python-typing": 0.34,
      "homelab-python-scripts": 0.21
    },
    "typing": {
      "general-python-typing": 0.89
    }
  },
  "doc_lengths": {
    "general-python-typing": 450,
    "homelab-python-scripts": 280
  },
  "avg_doc_length": 365.0,
  "doc_count": 42
}
```

**Known issue**: Written directly to file without tmp→replace (P0-1). Can be corrupted if daemon crashes during write.

### `vector_meta.json` — Vector Index Metadata

```json
{
  "general-python-typing": {
    "title": "Python Typing",
    "domain": "general",
    "vector_idx": 0
  },
  "homelab-python-scripts": {
    "title": "Python Scripts for Homelab",
    "domain": "homelab",
    "vector_idx": 1
  }
}
```

Companion file: `vector_index.faiss` — binary FAISS `IndexFlatL2`, float32, 384 dimensions (all-MiniLM-L6-v2 embedding size).

### `metadata.json` — Metadata Index

```json
{
  "by_domain": {
    "general": ["general-python-typing", "general-rust-intro"],
    "homelab": ["homelab-python-scripts"]
  },
  "by_kind": {
    "page": ["general-python-typing"],
    "entity": ["general-python-entity"],
    "concept": ["general-typing-concept"]
  },
  "by_tag": {
    "python": ["general-python-typing", "homelab-python-scripts"],
    "typing": ["general-python-typing"]
  },
  "by_status": {
    "published": ["general-python-typing"],
    "draft": ["homelab-python-scripts"]
  }
}
```

### `backlinks.json` — Backlink Index

```json
{
  "general-python-typing": ["general-mypy-guide", "homelab-ci-setup"],
  "general-mypy-guide": ["general-python-typing"]
}
```

### `graph_edges.json` — Graph Edge Index

```json
{
  "edges": [
    {
      "source": "general-python-typing",
      "target": "general-mypy-guide",
      "relationship": "references",
      "weight": 1.0
    }
  ]
}
```

### `relationships.json` — Extracted Relationships

```json
{
  "relationships": [
    {
      "subject": "Python",
      "predicate": "supports",
      "object": "type hints",
      "source_page_id": "general-python-typing",
      "confidence": 0.92
    }
  ]
}
```

## State Models

### `state/jobs.json` — Job Execution History

Written atomically by `JobExecutionStore` (the only index using `tmp → os.replace()`):

```json
{
  "inbox_scan": {
    "last_run": "2026-05-16T12:30:00Z",
    "last_status": "success",
    "last_result": {"files_processed": 3},
    "run_count": 142,
    "error_count": 0
  },
  "index_rebuild": {
    "last_run": "2026-05-16T12:00:00Z",
    "last_status": "success",
    "last_result": {
      "metadata_count": 42,
      "fulltext_count": 42,
      "vector_count": 42
    },
    "run_count": 8,
    "error_count": 0
  }
}
```

### `review_queue/{status}/{id}.json` — Review Items

```json
{
  "id": "review-abc123",
  "kind": "promotion_candidate",
  "page_id": "general-python-typing",
  "reason": "High cross-domain references (3 domains)",
  "status": "pending",
  "created_at": "2026-05-16T00:00:00Z",
  "updated_at": "2026-05-16T00:00:00Z",
  "notes": null
}
```

Status values: `pending | approved | rejected | deferred`

## Integration Models

### `NormalizedDocument`

Internal model produced by adapters, consumed by the ingestion pipeline:

```python
class NormalizedDocument(BaseModel):
    title: str
    content: str                    # Clean markdown
    source_path: Path
    adapter: str                    # Which adapter produced this
    metadata: dict[str, Any]        # Adapter-specific extras
    suggested_domain: str | None    # Adapter's domain suggestion (may be overridden by router)
```

### `IntegrationResult`

Produced by `DeterministicIntegrator`:

```python
class IntegrationResult(BaseModel):
    success: bool
    page_id: str
    action: str                     # "created" | "updated" | "skipped"
    before: dict[str, Any] | None   # Frontmatter before merge
    after: dict[str, Any]           # Frontmatter after merge
    changes: list[str]              # Human-readable change descriptions
    error: str | None
```

## Changelog Model

Stored as JSONL (`wiki_system/logs/changelog.jsonl`), one entry per line:

```json
{
  "timestamp": "2026-05-16T12:30:00Z",
  "operation": "ingest",
  "page_id": "general-python-typing",
  "domain": "general",
  "actor": "daemon:InboxScanJob",
  "summary": "Created page from notes.md",
  "before_hash": null,
  "after_hash": "sha256:abc123..."
}
```

## Extraction Result Models

Stored in page frontmatter after extraction:

```yaml
# Claims extracted by ClaimsExtractor
claims:
  - subject: "Python"
    predicate: "supports"
    object: "type hints since 3.5"
    confidence: 0.95

# Entities extracted by EntityExtractor
entities:
  - name: "Python"
    entity_type: "tool"
    aliases: ["CPython", "Python 3"]

# QA pairs extracted by QAExtractor
qa_pairs:
  - question: "When were type hints added to Python?"
    answer: "Type hints were added in Python 3.5 via PEP 484."

# Relationships extracted by RelationshipExtractor
extracted_relationships:
  - subject: "mypy"
    predicate: "implements"
    object: "Python type checking"
```

## File Naming Conventions

| Path pattern | Meaning |
|-------------|---------|
| `wiki_system/domains/{domain}/pages/{page_id}.md` | Published wiki page |
| `wiki_system/domains/{domain}/queue/{page_id}.md` | Page awaiting integration |
| `wiki_system/shared/{page_id}.md` | Cross-domain promoted page |
| `wiki_system/index/fulltext.json` | TF-IDF index |
| `wiki_system/index/vector_index.faiss` | FAISS binary |
| `wiki_system/index/vector_meta.json` | FAISS metadata |
| `wiki_system/exports/llms.txt` | Latest LLM-format export |
| `wiki_system/reports/governance_{ts}.md` | Governance run report |
| `wiki_system/state/jobs.json` | Job execution history |
| `wiki_system/review_queue/{status}/{id}.json` | Review item |
| `wiki_system/logs/changelog.jsonl` | Operation changelog |
