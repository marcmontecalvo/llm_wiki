# Governance System

Wiki quality maintenance and health monitoring.

## Overview

The governance system ensures wiki quality through automated checks and reporting:

- **Metadata Linting**: Validate frontmatter and structure
- **Staleness Detection**: Find outdated content
- **Quality Scoring**: Multi-factor quality assessment
- **Orphan Detection**: Find unreferenced pages
- **Automated Reporting**: Generate markdown reports

---

## Running Governance Checks

### CLI

```bash
# Run all governance checks
uv run llm-wiki govern check

# Rebuild indexes (if needed)
uv run llm-wiki govern rebuild-index
```

### Python API

```python
from pathlib import Path
from llm_wiki.daemon.jobs.governance import GovernanceJob

job = GovernanceJob(wiki_base=Path("wiki_system"))
stats = job.execute()

print(f"Total pages: {stats['total_pages']}")
print(f"Lint issues: {stats['lint_issues']}")
print(f"Stale pages: {stats['stale_pages']}")
print(f"Low quality: {stats['low_quality_pages']}")
```

### Daemon Automation

Configure in `config/daemon.yaml`:

```yaml
jobs:
  governance:
    enabled: true
    interval: 7200    # Run every 2 hours
```

---

## Governance Checks

### 1. Metadata Linting

**Purpose:** Validate frontmatter structure and required fields.

**Checks:**
- Required fields present (`id`, `title`, `domain`)
- Valid field types
- ID format (kebab-case)
- Domain exists in config
- Kind is valid (`page`, `entity`, `concept`, `source`)
- Tags format (list of strings)
- Dates in ISO 8601 format

**Severity Levels:**
- **Error**: Required fields missing, invalid types
- **Warning**: Recommended fields missing, format issues
- **Info**: Style suggestions

**Example Issues:**
```
ERROR: Missing required field 'id'
ERROR: Invalid domain 'unknown-domain'
WARNING: Missing recommended field 'summary'
WARNING: Tags should be lowercase
INFO: Consider adding source citation
```

**Implementation:** `src/llm_wiki/governance/linter.py`

---

### 2. Staleness Detection

**Purpose:** Identify outdated content that may need review.

**Criteria:**
- **Age-based**: Pages not updated in N days
- **Time-sensitive markers**: Content with dates, versions, "current"
- **Outdated references**: Links to old versions

**Staleness Levels:**
- **Fresh**: Updated within 30 days
- **Aging**: Updated 30-90 days ago
- **Stale**: Updated 90-180 days ago
- **Very stale**: Updated >180 days ago

**Time-Sensitive Indicators:**
- Date references (2023, 2024, etc.)
- Version numbers (v1.0, Python 3.9, etc.)
- Temporal language ("current", "latest", "recent")
- Scheduled events

**Example Output:**
```
STALE (120 days): python-programming
  - Contains "Python 3.9" (may be outdated)
  - Last updated: 2023-12-01

VERY STALE (200 days): api-design
  - Contains "current best practices"
  - No updates since: 2023-10-01
```

**Implementation:** `src/llm_wiki/governance/staleness.py`

---

### 3. Quality Scoring

**Purpose:** Multi-factor assessment of page quality.

**Scoring Factors:**

| Factor | Weight | Criteria |
|--------|--------|----------|
| **Content Length** | 25% | Sufficient content (>100 chars minimum, >500 ideal) |
| **Structure** | 20% | Has headings, lists, formatting |
| **Metadata** | 20% | Complete frontmatter, tags present |
| **Citations** | 15% | Source field or inline citations |
| **Freshness** | 10% | Recent updates |
| **Richness** | 10% | Entities, concepts extracted |

**Quality Levels:**
- **High** (80-100): Excellent quality, minimal issues
- **Medium** (60-79): Acceptable quality, room for improvement
- **Low** (<60): Needs significant improvement

**Example Scores:**
```
HIGH QUALITY (Score: 85)
  page-id: python-programming
  - Content: 1500 chars ✓
  - Structure: 5 headings, 3 lists ✓
  - Metadata: Complete ✓
  - Citations: Source present ✓
  - Freshness: Updated 10 days ago ✓

LOW QUALITY (Score: 45)
  page-id: quick-note
  - Content: 80 chars (too short) ✗
  - Structure: No headings ✗
  - Metadata: Missing summary ✗
  - Citations: No source ✗
  - Freshness: OK ✓
```

**Implementation:** `src/llm_wiki/governance/quality.py`

---

### 4. Orphan Detection

**Purpose:** Find pages with no incoming links.

**Detection:**
- Scan all pages for `[[page-id]]` links
- Identify pages not referenced by any other page
- Exclude intentional standalone pages

**Example Output:**
```
ORPHAN PAGES (3):
  - standalone-note
  - old-draft
  - test-page

Recommendation: Review for relevance, add links, or archive
```

**Note:** Entry points and index pages may be intentionally orphaned.

**Implementation:** `src/llm_wiki/governance/linter.py`

---

## Governance Reports

### Report Location

`wiki_system/reports/governance_YYYY-MM-DD_HH-MM-SS.md`

### Report Structure

```markdown
# Governance Report

Generated: 2024-01-15 14:30:00

## Summary

- Total pages: 50
- Lint issues: 5 (3 errors, 2 warnings)
- Stale pages: 8
- Low quality pages: 3
- Orphan pages: 2

## Lint Issues

### Errors (3)

**Page: broken-page**
- ERROR: Missing required field 'id'
- ERROR: Invalid domain 'unknown'

**Page: another-page**
- ERROR: Invalid field type for 'tags' (expected list, got string)

### Warnings (2)

**Page: incomplete-page**
- WARNING: Missing recommended field 'summary'
- WARNING: Tags should be lowercase

## Stale Pages (8)

**VERY STALE** (200+ days)
- api-design (last updated: 2023-10-01)
- old-notes (last updated: 2023-09-15)

**STALE** (90-180 days)
- python-guide (last updated: 2023-12-01)
- kubernetes-notes (last updated: 2023-11-20)
...

## Low Quality Pages (3)

**Score: 45** - quick-note
  - Content too short (80 chars)
  - No headings
  - Missing summary

**Score: 52** - draft-page
  - No source citation
  - Minimal structure

**Score: 58** - notes
  - Missing tags
  - Outdated (150 days)

## Orphan Pages (2)

- standalone-note
- test-page

## Recommendations

1. Fix 3 lint errors immediately
2. Review 8 stale pages for updates
3. Improve 3 low quality pages
4. Link or archive 2 orphan pages
```

---

## Planned Governance Features

See `IMPLEMENTATION_STATUS.md` for future enhancements:

### Contradiction Detection (#70)
- Detect conflicting claims across pages
- Semantic similarity analysis
- Negation detection
- Confidence scoring

### Review Queue (#71)
- Manual review workflow
- Review states (pending, approved, rejected)
- Reviewer assignment
- Review history

### Duplicate Detection (#72)
- Find duplicate entities/concepts
- Suggest merges
- Deduplication tools

### Retry Failed Ingests (#74)
- Track ingestion failures
- Automatic retry with backoff
- Error categorization

### Routing Mistakes (#75)
- Detect misrouted content
- Suggest rerouting
- Domain mismatch alerts

---

## Best Practices

### Regular Checks
```bash
# Weekly: Full governance check
uv run llm-wiki govern check

# Daily: Quick lint check
uv run llm-wiki govern check | grep ERROR
```

### Prioritization
1. **Fix errors first**: Lint errors block proper indexing
2. **Review stale pages**: Outdated info can mislead
3. **Improve low quality**: Better content = better retrieval
4. **Link orphans**: Integrate knowledge or archive

### Automation
- Run governance checks after bulk imports
- Schedule regular checks (daemon)
- Monitor quality trends over time

### Quality Targets
- **Lint errors**: 0
- **Stale pages**: <10%
- **Low quality pages**: <15%
- **Average quality score**: >70

---

## Governance Metrics

### Track Over Time

```python
from pathlib import Path
import re

# Parse report
report = Path("wiki_system/reports/governance_latest.md").read_text()

# Extract metrics
total_match = re.search(r"Total pages: (\d+)", report)
errors_match = re.search(r"(\d+) errors", report)
stale_match = re.search(r"Stale pages: (\d+)", report)

total_pages = int(total_match.group(1))
errors = int(errors_match.group(1))
stale = int(stale_match.group(1))

# Calculate percentages
error_rate = (errors / total_pages) * 100
stale_rate = (stale / total_pages) * 100

print(f"Error rate: {error_rate:.1f}%")
print(f"Stale rate: {stale_rate:.1f}%")
```

---

## Troubleshooting

### High Error Rate

**Causes:**
- Bulk import without validation
- Schema changes
- Manual edits

**Solutions:**
```bash
# Review errors
uv run llm-wiki govern check | grep ERROR

# Fix common issues
# - Add missing required fields
# - Validate domain IDs against config/domains.yaml
# - Check field types (tags should be list, not string)
```

### Many Stale Pages

**Causes:**
- Inactive domains
- One-time content dumps
- Archived knowledge

**Solutions:**
- Review and update relevant pages
- Archive truly historical content
- Set review schedules for time-sensitive topics

### Low Quality Scores

**Causes:**
- Quick notes without structure
- Incomplete drafts
- Copy-paste without cleanup

**Solutions:**
- Add summaries and tags
- Structure content with headings
- Add source citations
- Expand thin content

---

## See Also

- [CLI.md](CLI.md) - Governance commands
- [ARCHITECTURE.md](ARCHITECTURE.md) - Governance system design
- [CONFIG.md](CONFIG.md) - Daemon governance configuration
