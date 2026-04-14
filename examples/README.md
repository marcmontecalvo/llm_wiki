# LLM Wiki Examples

This directory contains example workflows demonstrating common usage patterns for the LLM wiki system.

## Examples Overview

### 01_basic_ingestion.py
**Demonstrates**: How to add content to the wiki system

- Drop files in inbox for automatic processing
- Add frontmatter metadata
- Process plain text files without frontmatter
- Trigger ingestion manually

**Use when**: You want to add new content to the wiki

```bash
uv run python examples/01_basic_ingestion.py
```

### 02_search_and_query.py
**Demonstrates**: How to search and query wiki content

- Fulltext search with TF-IDF scoring
- Domain-filtered search
- Tag-based queries
- Kind-based queries (page, entity, concept)
- Combined search with multiple filters
- Get specific pages by ID
- Find all pages in a domain

**Use when**: You need to find or retrieve wiki content

```bash
uv run python examples/02_search_and_query.py
```

### 03_governance_maintenance.py
**Demonstrates**: How to maintain wiki quality

- Run metadata linting checks
- Detect stale content
- Score page quality
- Generate governance reports
- Fix common issues

**Use when**: You want to maintain and improve wiki quality

```bash
uv run python examples/03_governance_maintenance.py
```

### 04_export_workflow.py
**Demonstrates**: How to export wiki content

- Export to llms.txt for LLM consumption
- Generate JSON sidecars for programmatic access
- Export graph for visualization
- Generate XML sitemap
- Run all exports via job

**Use when**: You need to use wiki content outside the system

```bash
uv run python examples/04_export_workflow.py
```

### 05_custom_adapter.py
**Demonstrates**: How to extend the system with custom adapters

- Create adapter for new file formats
- Extract metadata from custom formats
- Normalize to markdown
- Integrate adapter into system

**Use when**: You want to ingest files in unsupported formats

```bash
uv run python examples/05_custom_adapter.py
```

### 06_end_to_end_workflow.py
**Demonstrates**: Complete workflow from ingestion to export

- Add content via inbox
- Rebuild indexes
- Search content
- Run governance checks
- Export to multiple formats
- Use exports in downstream tools

**Use when**: You want to see how all components work together

```bash
uv run python examples/06_end_to_end_workflow.py
```

## Prerequisites

All examples assume:
- Wiki system initialized at `wiki_system/`
- Dependencies installed via `uv sync`
- Required directories exist (inbox, domains, index, exports)

## Running Examples

### Run individual example:
```bash
uv run python examples/01_basic_ingestion.py
```

### Run all examples:
```bash
for example in examples/*.py; do
    echo "Running $example..."
    uv run python "$example"
    echo "---"
done
```

## Integration with Claude Code

These workflows can also be executed via Claude Code skills:

```bash
# Search wiki
/wiki python --domain tech

# Add content
/ingest my-notes.md --domain tech

# Run governance
/govern

# Export content
/export
```

See `.claude/skills/` for skill implementations.

## Common Patterns

### 1. Adding Content

```python
from pathlib import Path

# Drop file in inbox
inbox = Path("wiki_system/inbox")
file_path = inbox / "my-page.md"
file_path.write_text("# My Page\n\nContent here...")

# Or use skill
/ingest my-page.md
```

### 2. Searching

```python
from llm_wiki.query.search import WikiQuery

wiki = WikiQuery()
results = wiki.search("python", domain="tech", tags=["programming"])
```

### 3. Quality Checks

```python
from llm_wiki.daemon.jobs.governance import GovernanceJob

job = GovernanceJob()
stats = job.execute()
print(f"Found {stats['lint_issues']} issues")
```

### 4. Exporting

```python
from llm_wiki.export.llmstxt import LLMSTxtExporter

exporter = LLMSTxtExporter()
path = exporter.export_all()
```

## Advanced Usage

### Custom Extractors

See `src/llm_wiki/extraction/` for examples of:
- Entity extraction
- Concept extraction
- Metadata enrichment

### Custom Exporters

See `src/llm_wiki/export/` for examples of:
- Format-specific exporters
- Domain-filtered exports
- Custom transformations

### Daemon Jobs

See `src/llm_wiki/daemon/jobs/` for examples of:
- Scheduled jobs
- Job orchestration
- Background processing

## Troubleshooting

### Issue: ImportError
**Solution**: Install in editable mode
```bash
uv pip install -e .
```

### Issue: Missing directories
**Solution**: Initialize wiki structure
```bash
mkdir -p wiki_system/{inbox,domains/{general,tech}/pages,index,exports,reports}
```

### Issue: No results from search
**Solution**: Rebuild indexes
```bash
uv run python -c "from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob; IndexRebuildJob().execute()"
```

## Next Steps

- Read [Architecture](../docs/ARCHITECTURE.md) for system design
- See [Setup Guide](../docs/SETUP.md) for installation
- Check [Agent Conventions](../docs/AGENT_CONVENTIONS.md) for guidelines
- Browse source code in `src/llm_wiki/`

## Support

- Issues: https://github.com/marcmontecalvo/llm_wiki/issues
- Documentation: `/docs/` directory
- Tests: `/tests/` for more usage examples
