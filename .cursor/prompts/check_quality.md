# Check Wiki Quality Prompt

Use this template to run governance and quality checks on the wiki.

## Full Governance Check

```
Run all governance checks on the wiki:

@govern check
```

This runs:
- Metadata validation (lint)
- Staleness detection
- Quality scoring
- Orphan page detection

## Rebuild Index

```
Rebuild the search indexes:

@govern rebuild-index
```

This rebuilds:
- Metadata index
- Fulltext index
- Backlink index
- Graph edge index

## View Reports

```
Show the latest governance report:

@govern report
```

Or manually:
```bash
cat wiki_system/reports/governance_latest.md
```

## Check Specific Domain

```
Run governance on a specific domain: [domain-name]

Example:
Run governance on: homelab
```

## Quality Metrics Explained

### Lint Issues
- Missing required frontmatter fields
- Invalid tag formats
- Domain assignment problems

### Stale Pages
- Pages not updated in >180 days
- Time-sensitive content that may be outdated

### Quality Score
- Content length (minimum 100 chars)
- Tag coverage
- Link density

### Orphan Pages
- Pages with no incoming links
- Potentially disconnected content

## Running from CLI

```bash
# Full governance check
uv run llm-wiki govern check

# Rebuild index
uv run llm-wiki govern rebuild-index

# Check specific domain
uv run llm-wiki govern check --domain homelab
```

## Interpretation Guide

| Metric | Good | Warning | Bad |
|--------|------|---------|-----|
| Lint Issues | 0 | 1-5 | >5 |
| Stale Pages | 0-5% | 5-15% | >15% |
| Quality Score | >0.7 | 0.5-0.7 | <0.5 |
| Orphan Pages | 0-2 | 3-10 | >10 |

## Automating Checks

To run governance automatically, start the daemon:
```bash
uv run llm-wiki daemon
```

The daemon can be configured to run governance checks periodically (see `config/daemon.yaml`).

## Common Fixes

### Fix Lint Issues
- Add missing frontmatter fields
- Fix tag format (use list: [tag1, tag2])
- Assign domains to unclassified pages

### Reduce Staleness
- Update old pages with current information
- Archive deprecated content
- Add "needs review" tags

### Improve Quality
- Add more content to thin pages
- Add tags to untagged pages
- Add internal links

### Address Orphans
- Add links from related pages
- Create index pages for topic areas