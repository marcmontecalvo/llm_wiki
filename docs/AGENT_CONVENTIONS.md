# Cross-Agent Wiki Conventions

Guidelines for agents working with the LLM wiki system.

## Page Identification

### Page IDs
- **Format**: `kebab-case` (lowercase with hyphens)
- **Examples**: `python-programming`, `api-design`, `docker-compose`
- **Uniqueness**: Page IDs must be unique across the entire wiki
- **Stability**: Once created, IDs should not change (breaks links)

### Page Titles
- **Format**: Natural language, proper capitalization
- **Examples**: "Python Programming", "API Design", "Docker Compose"
- **Length**: Keep under 80 characters

## Linking

### Internal Links
```markdown
Link to pages using double brackets: [[page-id]]
Example: See [[python-programming]] for details.
```

### Cross-Domain Links
```markdown
Links work across domains automatically.
[[vulpine-solutions/api-design]] and [[api-design]] both work if ID is unique.
```

### Backlinks
- System automatically tracks backlinks via metadata index
- Use `find_by_tag()` to find related pages
- Check `related_pages` field in metadata

## Frontmatter Schema

### Required Fields
```yaml
---
id: page-id              # Unique identifier
title: Page Title        # Human-readable title
domain: domain-name      # Domain (see config/domains.yaml)
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

### Optional Fields
```yaml
status: active           # active, draft, archived
entities:                # Extracted entities
  - name: Entity Name
    type: technology
    description: Brief description
concepts:                # Extracted concepts
  - name: Concept Name
    description: Brief description
related_pages:           # Explicit relationships
  - related-page-id
claims:                  # Extracted factual claims (auto-populated by pipeline)
  - text: "Python was first released in 1991"
    source_ref: "paragraph 1"
    confidence: 0.95       # 0.0-1.0; >= 0.8 considered high confidence
    page_id: page-id       # which page this claim is on
    temporal_context: "initial release"  # optional: when this was true
    qualifiers: []         # optional: conditions/limitations on the claim
    evidence: null         # optional: supporting evidence text
```

### Claims Format
- **text**: Atomic, declarative, verifiable statement (one fact per claim)
- **source_ref**: Where in the content (e.g., "paragraph 2", "section title")
- **confidence**: `1.0` = explicit/well-supported; `0.6–0.7` = less explicit; `< 0.4` = very uncertain
- **temporal_context**: When the claim is/was true (e.g., "as of 2024", "during 2020–2023")
- **qualifiers**: Conditions limiting the claim (e.g., "in the US", "for adults")
- Claims are extracted for all page kinds and stored in the metadata index for cross-page search

## Domain Boundaries

### Domain Purpose
See `config/domains.yaml` for complete list. Example domains:
- **vulpine-solutions**: MSP, operations, sales, security, client delivery
- **home-assistant**: Automation, voice assistant, ESP32, local AI, sensors
- **homelab**: Proxmox, k3s, storage, networking, GPUs, services
- **personal**: Family logistics, hobbies, plans, notes
- **general**: Fallback bucket for unclassified or low-confidence content

### Routing Rules
1. Explicit domain in frontmatter (highest priority)
2. Folder-based routing (`inbox/{domain}/`)
3. Content-based classification
4. Fallback to `general`

### Cross-Domain Entities
Entities/concepts appearing in multiple domains:
- Live in their primary domain
- Referenced from other domains via links
- May be promoted to `shared/` (future feature)

## Content Guidelines

### Markdown Format
- Use standard CommonMark markdown
- Headings: `#` for title, `##` for sections
- Lists: `-` for bullets, `1.` for numbered
- Code: Triple backticks with language

### Citations
Always include source when adding factual content:
```yaml
---
source: https://example.com/article
---
```

Or inline:
```markdown
According to [Source](https://example.com), ...
```

### Quality Standards
- **Minimum length**: 100 characters
- **Structure**: Use headings and lists
- **Summary**: Add 1-2 sentence summary
- **Tags**: Add 2-5 relevant tags
- **Source**: Cite sources for factual claims

## Export Formats

### llms.txt
- LLM-optimized plain text
- Metadata as HTML comments
- Summary as blockquote
- Body as clean markdown

Example:
```
# Page Title

<!-- id: page-id -->
<!-- domain: general -->
<!-- tags: tag1, tag2 -->

> Brief summary of the page.

Content goes here...
```

### JSON Sidecar
- Full metadata as JSON
- Computed fields (word_count, char_count)
- Same path as .md file with .json extension

```json
{
  "id": "page-id",
  "title": "Page Title",
  "domain": "general",
  "tags": ["tag1", "tag2"],
  "_computed": {
    "word_count": 150,
    "char_count": 900,
    "has_content": true
  }
}
```

### Graph Format
- Nodes: Pages with metadata
- Edges: Links between pages
- Format: JSON with `nodes` and `edges` arrays

```json
{
  "nodes": [
    {
      "id": "page-id",
      "label": "Page Title",
      "domain": "general",
      "kind": "page",
      "tags": ["tag1"]
    }
  ],
  "edges": [
    {
      "source": "page-a",
      "target": "page-b",
      "type": "link"
    }
  ]
}
```

## Search & Query

### Fulltext Search
```python
results = wiki.search(
    query="search terms",
    domain="vulpine-solutions",  # Optional filter
    kind="entity",               # Optional filter
    tags=["python"],             # Optional filter
    limit=10
)
```

### Metadata Query
```python
# By tag
pages = wiki.find_by_tag("python")

# By kind
entities = wiki.find_by_kind("entity")

# By domain
tech_pages = wiki.find_by_domain("vulpine-solutions")

# Get specific page
page = wiki.get_page("page-id")
```

## Agent Workflows

### Adding Content
1. Drop file in `wiki_system/inbox/`
2. Optionally add domain in frontmatter
3. Wait for daemon to process
4. Check `domains/{domain}/queue/` for output

### Querying
1. Use `/wiki` skill or `WikiQuery` class
2. Filter by domain/kind/tags as needed
3. Results include relevance scores

### Maintenance
1. Run `/govern` to check quality
2. Review governance report
3. Fix high-priority issues (errors)
4. Consider low-quality pages for improvement

### Exporting
1. Run `/export` for all formats
2. Use `exports/llms.txt` for LLM context
3. Use `exports/graph.json` for visualization
4. Use JSON sidecars for programmatic access

## Best Practices

### For Agents
- Always check if page exists before creating
- Use search to find existing content
- Add meaningful summaries
- Tag appropriately
- Cite sources

### For Humans
- Review governance reports regularly
- Fix lint errors promptly
- Update stale content
- Remove orphan pages
- Monitor quality scores

### For Systems
- Run governance checks after bulk imports
- Rebuild indexes after significant changes
- Export regularly for backup
- Monitor growth of each domain
