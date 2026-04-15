# llms-full.txt Export

## Overview

The `llms-full.txt` export format provides comprehensive, machine-readable documentation of your entire wiki with structured metadata, extracted insights, and relationship information. Unlike the basic `llms.txt`, which includes only page content and simple metadata, `llms-full.txt` includes:

- All metadata fields (confidence scores, dates, tags, entity types, etc.)
- Extracted entities and concepts from page content
- Extracted claims with confidence scores
- Extracted relationships between entities
- Backlinks and forward links (bidirectional relationships)
- Structured sections for easy LLM parsing and fine-tuning

This format is ideal for:
- **LLM Fine-tuning**: Train models on comprehensive, structured knowledge
- **RAG Systems**: Provide rich context for retrieval-augmented generation
- **Knowledge Base Transfer**: Export and migrate entire wikis between systems
- **Comprehensive Backups**: Preserve all metadata alongside content
- **AI Research**: Analyze structured knowledge representation

## File Format

Each page in `llms-full.txt` follows this structured template:

```markdown
# Page Title

<!-- Metadata -->
- id: page-id
- domain: domain-name
- kind: entity|page|concept|source
- status: published|draft|archived|review
- confidence: 0.85
- created_at: 2024-01-01T00:00:00
- updated_at: 2024-02-01T00:00:00
- entity_type: Programming Language
- tags: python, programming, backend
- sources: https://example.com; https://reference.com

<!-- Summary -->
> Brief one-sentence summary of the page

<!-- Content -->

Main page content goes here...

## Main Section

Detailed content about the topic...

<!-- Entities -->

#### Entity Name
- Type: Entity Type
- Description: What this entity is
- Aliases: Alt Name 1, Alt Name 2
- Confidence: 0.95
- Context: Where mentioned in content

#### Another Entity
...

<!-- Concepts -->

#### Concept Name
- Definition: The definition of this concept
- Category: Concept Category
- Related: Related Concept 1, Related Concept 2
- Confidence: 0.92
- Examples: Example 1; Example 2; Example 3

#### Another Concept
...

<!-- Claims -->

- Factual claim statement (95%)
  - subject=Python, predicate=is, object=interpreted
  - temporal: since 1991
  - qualifiers: in most implementations

- Another factual claim (85%)
  - subject=..., predicate=..., object=...

<!-- Relationships -->

- Entity A --[relationship_type]--> Entity B (98%)
  - Description of the relationship

- Entity X <--[bidirectional_type]--> Entity Y (90%)

<!-- Links -->

**Links (from metadata):**
- [[related-page]]

**Forward links:**
- [[pip]]
- [[virtualenv]]

**Backlinks:**
- [[web-development]]
- [[data-science]]

**Broken links (targets not found):**
- [[nonexistent-page]]

---
```

### Section Breakdown

#### Metadata Section
Contains all page properties including:
- `id`: Unique page identifier
- `domain`: Domain the page belongs to
- `kind`: Page type (entity, concept, page, source)
- `status`: Publication status
- `confidence`: Quality/confidence score (0.0-1.0)
- `created_at` / `updated_at`: Timestamps
- `entity_type`: For entity pages, the entity classification
- `tags`: Categorization tags
- `sources`: Reference URLs

#### Summary Section
Optional one-sentence summary from page metadata.

#### Content Section
The full page body content in markdown.

#### Entities Section
Extracted named entities from the page:
- Entity name and type
- Description and aliases
- Extraction confidence
- Context where mentioned

#### Concepts Section
Extracted conceptual information:
- Concept definitions
- Related concepts
- Category classification
- Usage examples

#### Claims Section
Extracted factual claims with confidence:
- Claim statement with confidence percentage
- Subject-Predicate-Object triplet (if identified)
- Temporal context (when the claim is true)
- Qualifiers and conditions

#### Relationships Section
Extracted relationships between entities:
- Direction (unidirectional or bidirectional)
- Relationship type
- Confidence score
- Optional description

#### Links Section
Bidirectional link information:
- **Metadata links**: Links in page metadata
- **Forward links**: Pages this page links to
- **Backlinks**: Pages that link to this page
- **Broken links**: Non-existent link targets

## Usage

### Command Line

Export all domains:
```bash
llm-wiki export llmsfull
```

Export with options:
```bash
# Export specific domain
llm-wiki export llmsfull --domain tech

# Filter by quality score (only include pages with confidence >= 0.8)
llm-wiki export llmsfull --min-quality 0.8

# Limit number of pages
llm-wiki export llmsfull --max-pages 1000

# Custom output file
llm-wiki export llmsfull --output exports/my-knowledge.txt

# Combine options
llm-wiki export llmsfull \
  --domain tech \
  --min-quality 0.7 \
  --max-pages 500 \
  --output exports/tech-knowledge.txt
```

### Python API

```python
from llm_wiki.export.llmsfull import LLMSFullExporter
from pathlib import Path

# Initialize exporter
exporter = LLMSFullExporter(wiki_base=Path("wiki_system"))

# Export all pages
output_path = exporter.export_all()

# Export with filters
output_path = exporter.export_all(
    min_quality=0.8,  # Only pages with confidence >= 0.8
    max_pages=500,     # Export at most 500 pages
)

# Export specific domain
output_path = exporter.export_domain(
    "tech",
    min_quality=0.7,
    max_pages=200,
)

# Get statistics
stats = exporter.get_export_stats()
print(f"Total pages: {stats['total_pages']}")
print(f"Pages with extractions: {stats['pages_with_extractions']}")
print(f"Pages with backlinks: {stats['pages_with_backlinks']}")

# Export single page
page_export = exporter.export_page(
    Path("wiki_system/domains/tech/pages/python.md"),
    include_extractions=True,
    include_links=True,
)
```

## Size Management

`llms-full.txt` files can be large depending on your wiki size. Use filtering options to manage file sizes:

```bash
# Small export (high quality only, limited pages)
llm-wiki export llmsfull --min-quality 0.9 --max-pages 100

# Medium export (good quality, reasonable limit)
llm-wiki export llmsfull --min-quality 0.7 --max-pages 500

# Full export (all pages)
llm-wiki export llmsfull
```

### Estimated Sizes

For reference, typical sizes are approximately:

- **Per page**: 2-10 KB (page content + metadata)
- **With extractions**: +5-20 KB (entities, concepts, claims, relationships)
- **1,000 pages**: 5-30 MB
- **5,000 pages**: 25-150 MB
- **10,000+ pages**: 50-300+ MB

Consider using domain-specific exports or quality filters for larger wikis.

## Use Cases

### 1. LLM Fine-tuning

Use comprehensive `llms-full.txt` for fine-tuning domain-specific models:

```python
import openai

# Load the exported data
with open("exports/llms-full.txt") as f:
    training_data = f.read()

# Use for fine-tuning (example with OpenAI)
# training_file = openai.File.create(
#     file=open("exports/llms-full.txt", "rb"),
#     purpose="fine-tune",
# )
```

### 2. RAG System Ingestion

Use for building retrieval-augmented generation systems:

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma

# Load and split the document
with open("exports/llms-full.txt") as f:
    text = f.read()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["---\n", "\n\n", "\n", ""],
)
chunks = splitter.split_text(text)

# Create embeddings and store
embeddings = OpenAIEmbeddings()
vectorstore = Chroma.from_texts(
    chunks,
    embeddings,
    persist_directory="./chroma_db",
)
```

### 3. Knowledge Transfer

Transfer your knowledge base to another system:

```bash
# Export from source wiki
llm-wiki export llmsfull --output knowledge.txt

# Transfer file to new location/system
scp knowledge.txt user@newhost:/data/

# Parse and import in target system
# (System-specific import logic)
```

### 4. Analysis and Reporting

Parse the structured format for analysis:

```python
import re

with open("exports/llms-full.txt") as f:
    content = f.read()

# Count pages
pages = len(re.findall(r"^# (?!Domain:)", content, re.MULTILINE))

# Find all claims
claims = re.findall(r"^- .+ \(\d+%\)$", content, re.MULTILINE)

# Count entities
entities = len(re.findall(r"^#### ", content, re.MULTILINE))

print(f"Pages: {pages}")
print(f"Claims: {len(claims)}")
print(f"Entities: {entities}")
```

## Filtering Options

### Quality/Confidence Filtering

The `--min-quality` flag filters pages by confidence score:

```bash
# Only include high-confidence pages (>= 0.9)
llm-wiki export llmsfull --min-quality 0.9

# Include all pages with reasonable quality (>= 0.6)
llm-wiki export llmsfull --min-quality 0.6
```

### Page Limit

The `--max-pages` flag limits the number of pages exported:

```bash
# Export first 100 pages
llm-wiki export llmsfull --max-pages 100

# Export first 1000 pages
llm-wiki export llmsfull --max-pages 1000
```

### Domain-Specific Export

Export only specific domains:

```bash
# Just the tech domain
llm-wiki export llmsfull --domain tech

# Just the science domain
llm-wiki export llmsfull --domain science

# Can combine with other filters
llm-wiki export llmsfull --domain tech --min-quality 0.8 --max-pages 500
```

## Parsing the Format

The structured format with HTML comments makes it easy to parse programmatically:

```python
import re
from pathlib import Path

def parse_llms_full(file_path: str) -> list[dict]:
    """Parse llms-full.txt into structured pages."""
    content = Path(file_path).read_text()

    # Split by page separator
    pages_raw = content.split("---\n")

    pages = []
    for page_text in pages_raw:
        if not page_text.strip():
            continue

        # Extract sections
        page = {}

        # Title
        title_match = re.search(r"^# (.+)$", page_text, re.MULTILINE)
        if title_match:
            page["title"] = title_match.group(1)

        # Metadata
        metadata_match = re.search(
            r"<!-- Metadata -->(.+?)(?:<!-- |$)",
            page_text,
            re.DOTALL
        )
        if metadata_match:
            metadata_text = metadata_match.group(1)
            page["metadata"] = {}
            for line in metadata_text.strip().split("\n"):
                if line.startswith("- "):
                    key, value = line[2:].split(": ", 1)
                    page["metadata"][key] = value

        # Content
        content_match = re.search(
            r"<!-- Content -->(.+?)(?:<!-- |$)",
            page_text,
            re.DOTALL
        )
        if content_match:
            page["content"] = content_match.group(1).strip()

        # Extract entities
        entities_match = re.findall(
            r"^#### (.+)$",
            page_text,
            re.MULTILINE
        )
        page["entities"] = entities_match

        # Extract claims
        claims_match = re.findall(
            r"^- (.+?) \((\d+)%\)$",
            page_text,
            re.MULTILINE
        )
        page["claims"] = claims_match

        pages.append(page)

    return pages
```

## Format Design Principles

The format is designed with several principles in mind:

1. **LLM-Friendly**: Uses clear sections, consistent structure, and semantic HTML comments for easy parsing by language models.

2. **Hierarchical**: Structured sections allow LLMs to understand page importance and relationships.

3. **Extraction-Ready**: Extracted data (entities, claims, relationships) is explicitly formatted for machine consumption.

4. **Human-Readable**: Despite being optimized for machines, the format remains readable and understandable by humans.

5. **Extensible**: New sections can be added without breaking existing parsers.

6. **Compression-Friendly**: Repetitive structure compresses well with gzip or brotli.

## Related Features

- **Backlink Tracking**: Uses backlink index from #69 for relationship information
- **Claims Extraction**: Includes extracted claims from #66
- **Relationship Extraction**: Includes extracted relationships from #67
- **JSON Sidecars**: For per-page metadata, see `json-sidecar` export

## Troubleshooting

### Large File Sizes

If the exported file is too large:
- Use `--max-pages` to limit pages
- Use `--min-quality` to filter low-confidence pages
- Export specific domains with `--domain`

### Missing Extraction Data

If extraction sections are empty:
- Run content extraction first: `llm-wiki extract claims` and `llm-wiki extract relationships`
- Check that extraction files exist in `wiki_system/index/`

### Broken Links

If many broken links appear:
- Verify all referenced pages exist
- Run backlink index rebuild: `llm-wiki index rebuild-backlinks`

## Performance

Typical export times:
- **100 pages**: < 1 second
- **1,000 pages**: 2-5 seconds
- **10,000 pages**: 20-60 seconds

File I/O is the bottleneck; extraction loading is cached.
