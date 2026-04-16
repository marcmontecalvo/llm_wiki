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

## Code Patterns

### Adding a New Extractor

Create a new extractor class in `src/llm_wiki/extraction/` following this pattern:

```python
"""Name extractor for extracting entity names from content.

This is called by the extraction pipeline to find mentions
of specific entity types in content before routing to
the appropriate domain.

Called by: ExtractionPipeline.run()
Returns: List of extracted entities with type, name, and context.
"""

from pathlib import Path
from llm_wiki.extraction.base import BaseExtractor


class NameExtractor(BaseExtractor):
    """Extract named entities from content."""

    def extract(self, content: str, metadata: dict) -> list[dict]:
        """Extract entities from content.

        Args:
            content: The raw content to extract from
            metadata: Page metadata dict with id, domain, etc.

        Returns:
            List of dicts with keys: name, type, context, confidence

        Example:
            >>> extractor = NameExtractor()
            >>> entities = extractor.extract("Python 3.12 was released...", {})
            >>> print(entities[0]["name"])
            "Python"
        """
        results = []
        # Implementation here
        return results
```

Key components:
- Inherit from `BaseExtractor`
- Implement `extract(content, metadata)` method
- Return list of dicts with extracted data
- Include docstring with Args, Returns, Example

### Adding a New Export Format

Create a new exporter class in `src/llm_wiki/export/`:

```python
"""Custom exporter for wiki content.

This is called by the export pipeline to generate
custom output formats from wiki pages.

Called by: ExportJob with --format flag
Returns: Path to generated export file.
"""

from pathlib import Path
from llm_wiki.export.base import BaseExporter


class CustomExporter(BaseExporter):
    """Export wiki pages to custom format."""

    def export(self, pages: list[dict], output_path: Path) -> Path:
        """Export pages to custom format.

        Args:
            pages: List of page dicts with content and metadata
            output_path: Destination path for export

        Returns:
            Path to the generated export file

        Example:
            >>> exporter = CustomExporter(wiki_base=Path("wiki_system"))
            >>> path = exporter.export(pages, Path("output.txt"))
            >>> print(path)
            PosixPath("output.txt")
        """
        # Implementation here
        return output_path
```

### Adding CLI Commands

Add new Click commands in `src/llm_wiki/cli.py`:

```python
# Add new command to the CLI
@importmain.command("name")
@click.argument("name")
@click.option("--domain", help="Domain to use")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def command_name(name: str, domain: str | None, verbose: bool) -> None:
    """A helpful command description.

    Longer description of what this command does.
    Shows in --help output.
    """
    # Implementation here
    click.echo(f"Running {name}" if verbose else name)
```

## Testing Patterns

### Using Pytest Fixtures

The wiki provides pytest fixtures in `tests/conftest.py`:

```python
import pytest
from pathlib import Path
from llm_wiki.query.search import WikiQuery


@pytest.fixture
def wiki_base(tmp_path):
    """Create a temporary wiki for testing.

    This fixture creates a minimal wiki structure
    with test data and cleans up after tests.
    """
    wiki = WikiQuery(wiki_base=tmp_path)
    # Add test data
    return wiki


@pytest.fixture
def sample_page():
    """Sample page for testing."""
    return {
        "id": "test-page",
        "title": "Test Page",
        "domain": "general",
        "content": "# Test Page\\n\\nThis is test content."
    }


def test_search(wiki_base, sample_page):
    """Test search returns expected results."""
    results = wiki_base.search("test")
    assert len(results) > 0
```

### Mocking LLM Calls

Mock external dependencies in tests:

```python
from unittest.mock import Mock, patch


@patch("llm_wiki.extraction.service.OpenAI")
def test_extraction_with_mock(mock_openai):
    """Test extraction with mocked LLM."""
    mock_client = Mock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_openai.return_value = mock_client

    from llm_wiki.extraction.service import ExtractionService
    service = ExtractionService()
    results = service.extract("content")
    assert results is not None
```

### Coverage Targets

- Aim for >90% coverage on new code
- Required: 100% on CLI commands
- Required: All extractors and exporters tested
- Run: `uv run pytest --cov=src/llm_wiki --cov-report=term-missing`

## Common Tasks

### Add a New Domain

1. Edit `config/domains.yaml`:
```yaml
domains:
  new-domain:
    description: "Domain description"
    routing:
      patterns:
        - "newdomain/*"
```

2. Create directory: `wiki_system/domains/new-domain/`

### Add a New Governance Check

1. Create file in `src/llm_wiki/governance/checks/new_check.py`:
```python
"""New governance check.

This check validates X in wiki pages.
Run by: GovernanceJob.execute()
"""

from llm_wiki.governance.base import BaseCheck


class NewCheck(BaseCheck):
    """Description of what this check does."""

    def run(self, pages: list[dict]) -> list[dict]:
        """Run the governance check.

        Args:
            pages: List of page dicts

        Returns:
            List of issue dicts with severity, message, page_id
        """
        issues = []
        # Check implementation
        return issues
```

2. Register in `src/llm_wiki/governance/__init__.py`

### Add a New Export Format

1. Create exporter in `src/llm_wiki/export/new_format.py`:
```python
"""New format exporter.

This is called by ExportJob with --format=new_format.
"""

from llm_wiki.export.base import BaseExporter
# ... implementation
```

2. Register in `src/llm_wiki/export/__init__.py`