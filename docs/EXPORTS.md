# Export Formats

Documentation for all wiki export formats.

## Overview

The wiki system exports content in multiple machine-readable formats optimized for different use cases:

| Format | Purpose | Location | Command |
|--------|---------|----------|---------|
| llms.txt | LLM context loading | `exports/llms.txt` | `llm-wiki export llmstxt` |
| JSON Sidecars | Programmatic access | `domains/{domain}/pages/*.json` | `llm-wiki export all` |
| Graph | Visualization | `exports/graph.json` | `llm-wiki export graph` |
| Sitemap | Navigation | `exports/sitemap.xml` | `llm-wiki export all` |

---

## llms.txt

**Purpose:** LLM-optimized context file for loading wiki content into language models.

**Location:** `wiki_system/exports/llms.txt`

**Format:** Plain text markdown with metadata as HTML comments.

**Generation:**
```bash
uv run llm-wiki export llmstxt
```

**Structure:**
```markdown
# Page Title

<!-- id: page-id -->
<!-- domain: domain-name -->
<!-- kind: page -->
<!-- tags: tag1, tag2, tag3 -->
<!-- source: https://example.com -->

> Brief summary of the page content.

## Section 1

Content goes here...

## Section 2

More content...

---

# Next Page Title

<!-- id: next-page-id -->
...
```

**Features:**
- All pages concatenated into single file
- Metadata preserved as HTML comments (invisible to LLMs but parseable)
- Summaries as blockquotes for easy skimming
- Clean markdown body
- Pages separated by `---` dividers

**Use Cases:**
- Loading into LLM context windows
- Agent knowledge base initialization
- Full-text search preparation
- Backup/archival

**Example:**
```python
from pathlib import Path

# Read entire wiki for LLM context
llms_txt = Path("wiki_system/exports/llms.txt").read_text()

# Use in LLM prompt
prompt = f"Context:\n{llms_txt}\n\nQuestion: ..."
```

---

## JSON Sidecars

**Purpose:** Per-page metadata for programmatic access.

**Location:** `wiki_system/domains/{domain}/pages/{page-id}.json` (alongside each .md file)

**Format:** JSON object with full frontmatter + computed fields.

**Generation:**
```bash
uv run llm-wiki export all
```

**Structure:**
```json
{
  "id": "page-id",
  "title": "Page Title",
  "domain": "domain-name",
  "kind": "page",
  "summary": "Brief summary",
  "tags": ["tag1", "tag2"],
  "source": "https://example.com",
  "created": "2024-01-01T00:00:00Z",
  "updated": "2024-01-02T00:00:00Z",
  "entities": [
    {
      "name": "Entity Name",
      "type": "technology",
      "description": "Brief description"
    }
  ],
  "concepts": [
    {
      "name": "Concept Name",
      "description": "Brief description"
    }
  ],
  "_computed": {
    "word_count": 150,
    "char_count": 900,
    "has_content": true,
    "has_summary": true,
    "has_tags": true,
    "tag_count": 2,
    "entity_count": 1,
    "concept_count": 1
  }
}
```

**Features:**
- Full frontmatter metadata
- Extracted entities and concepts
- Computed metrics (word count, character count)
- Validation flags (has_content, has_summary, etc.)
- One JSON file per markdown file

**Use Cases:**
- Programmatic wiki queries
- Building indexes
- Analytics and reporting
- Integration with other tools

**Example:**
```python
import json
from pathlib import Path

# Load page metadata
page_json = Path("wiki_system/domains/general/pages/python.json")
metadata = json.loads(page_json.read_text())

print(f"Title: {metadata['title']}")
print(f"Tags: {', '.join(metadata['tags'])}")
print(f"Word count: {metadata['_computed']['word_count']}")
```

---

## Graph Export

**Purpose:** Page relationship graph for visualization and traversal.

**Location:** `wiki_system/exports/graph.json`

**Format:** JSON with nodes and edges arrays.

**Generation:**
```bash
uv run llm-wiki export graph
```

**Structure:**
```json
{
  "nodes": [
    {
      "id": "page-id",
      "label": "Page Title",
      "domain": "domain-name",
      "kind": "page",
      "tags": ["tag1", "tag2"],
      "summary": "Brief summary"
    },
    {
      "id": "another-page",
      "label": "Another Page",
      "domain": "domain-name",
      "kind": "entity",
      "tags": ["tag3"]
    }
  ],
  "edges": [
    {
      "source": "page-id",
      "target": "another-page",
      "type": "link"
    }
  ]
}
```

**Features:**
- Nodes: All pages with key metadata
- Edges: Links between pages
- Domain preservation
- Tag metadata for filtering

**Use Cases:**
- Graph visualization (D3.js, Cytoscape, etc.)
- Network analysis
- Finding related content
- Detecting clusters and communities

**Example:**
```python
import json
from pathlib import Path

# Load graph
graph = json.loads(Path("wiki_system/exports/graph.json").read_text())

# Find pages in a domain
homelab_pages = [
    node for node in graph["nodes"]
    if node["domain"] == "homelab"
]

# Find connections
for edge in graph["edges"]:
    print(f"{edge['source']} -> {edge['target']}")
```

**Note:** Current implementation extracts `[[page-id]]` links from markdown. Future enhancements (#69) will add backlink tracking and more relationship types.

---

## Sitemap

**Purpose:** XML sitemap for navigation and indexing.

**Location:** `wiki_system/exports/sitemap.xml`

**Format:** Standard XML sitemap.

**Generation:**
```bash
uv run llm-wiki export all
```

**Structure:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>file:///path/to/wiki_system/domains/general/pages/page-id.md</loc>
    <lastmod>2024-01-02T00:00:00Z</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>file:///path/to/wiki_system/domains/tech/pages/another-page.md</loc>
    <lastmod>2024-01-01T00:00:00Z</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
</urlset>
```

**Features:**
- Standard sitemap.xml format
- File:// URLs (local filesystem)
- Last modified timestamps
- Change frequency estimates
- Priority values

**Use Cases:**
- Wiki navigation tools
- Change tracking
- Backup planning
- Integration with site generators

**Example:**
```python
import xml.etree.ElementTree as ET

# Parse sitemap
tree = ET.parse("wiki_system/exports/sitemap.xml")
root = tree.getroot()

# List all pages
for url in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
    loc = url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc").text
    lastmod = url.find("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod").text
    print(f"{loc} - Last modified: {lastmod}")
```

---

## Export Automation

### CLI Usage

```bash
# Export all formats
uv run llm-wiki export all

# Export specific format
uv run llm-wiki export llmstxt
uv run llm-wiki export graph

# Custom output location
uv run llm-wiki export llmstxt --output custom-path.txt
uv run llm-wiki export graph --output custom-graph.json
```

### Python API

```python
from pathlib import Path
from llm_wiki.export.llmstxt import LLMSTxtExporter
from llm_wiki.export.graph import GraphExporter
from llm_wiki.export.json_sidecar import JSONSidecarExporter
from llm_wiki.export.sitemap import SitemapGenerator

wiki_base = Path("wiki_system")

# Export llms.txt
llmstxt = LLMSTxtExporter(wiki_base=wiki_base)
path = llmstxt.export_all()

# Export graph
graph = GraphExporter(wiki_base=wiki_base)
graph_path = graph.export_json()

# Export JSON sidecars
json_exporter = JSONSidecarExporter(wiki_base=wiki_base)
count = json_exporter.export_all()

# Export sitemap
sitemap = SitemapGenerator(wiki_base=wiki_base)
sitemap_path = sitemap.generate()
```

### Daemon Automation

Configure in `config/daemon.yaml`:

```yaml
jobs:
  export:
    enabled: true
    interval: 3600    # Export every hour
```

---

## Output Validation

All exports are validated before writing:

- **llms.txt**: UTF-8 encoding, valid markdown
- **JSON sidecars**: Valid JSON, schema compliance
- **Graph**: Valid JSON, nodes/edges structure
- **Sitemap**: Valid XML, sitemap schema

---

## Future Enhancements

See `IMPLEMENTATION_STATUS.md` for planned export features:

- **llms-full.txt** (#73): Comprehensive export with all metadata
- **Markdown exports**: Cleaned markdown without frontmatter
- **RSS feeds**: Change feeds for updates
- **HTML generation**: Static site generation

---

## See Also

- [CLI.md](CLI.md) - Export commands
- [ARCHITECTURE.md](ARCHITECTURE.md) - Export pipeline architecture
- [CONFIG.md](CONFIG.md) - Daemon export configuration
