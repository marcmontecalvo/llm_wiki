# Page Promotion System

## Overview

The promotion system automatically identifies domain-local pages that are referenced across multiple domains and promotes them to the shared space. This ensures that commonly used content is centralized and reduces duplication.

## Architecture

### Key Components

1. **PromotionConfig** (`promotion/config.py`)
   - Configuration schema for promotion parameters
   - Thresholds for auto-promotion vs. review queue
   - Quality score requirements
   - Scoring weights

2. **PromotionScorer** (`promotion/scorer.py`)
   - Analyzes pages for promotion eligibility
   - Calculates promotion scores based on:
     - Cross-domain references count
     - Total reference count
     - Page quality score
     - Page age

3. **PromotionEngine** (`promotion/engine.py`)
   - Main promotion orchestrator
   - Handles page promotion workflow
   - Creates shared copies and tombstones
   - Updates backlinks index
   - Integrates with review queue

4. **PromotionJob** (`daemon/jobs/promotion.py`)
   - Daemon job for periodic promotion checks
   - Generates reports
   - Scheduled via daemon configuration

## Promotion Scoring Algorithm

The promotion score is calculated as:

```
promotion_score = (
    cross_domain_references * 2.0 +
    total_references * 0.5 +
    quality_score * 1.0 +
    age_factor * 0.3
)
```

Where:
- `cross_domain_references`: Count of pages in different domains that link to this page
- `total_references`: Total count of all pages linking to this page
- `quality_score`: Page quality (0.0-1.0) calculated by QualityScorer
- `age_factor`: Page age factor (newer = higher, capped at 365 days)

### Default Thresholds

- **Auto-promote**: Score ≥ 10.0 (if require_approval=False)
- **Suggest for review**: Score ≥ 5.0
- **Minimum quality**: 0.6
- **Minimum cross-domain refs**: 2

## Configuration

### Daemon Configuration (`config/daemon.yaml`)

```yaml
daemon:
  # ... other settings ...
  promotion_every_hours: 24  # Check for promotions every 24 hours
  promotion:
    enabled: true
    auto_promote_threshold: 10.0
    suggest_promote_threshold: 5.0
    min_quality_score: 0.6
    min_cross_domain_refs: 2
    require_approval: true  # Use review queue vs auto-promote
```

### Promotion-Specific Config

All configuration values are in `PromotionConfig`:

```python
from llm_wiki.promotion.config import PromotionConfig

config = PromotionConfig(
    auto_promote_threshold=10.0,
    suggest_promote_threshold=5.0,
    min_quality_score=0.6,
    min_cross_domain_refs=2,
    require_approval=True,
    cross_domain_ref_weight=2.0,
    total_ref_weight=0.5,
    quality_weight=1.0,
    age_weight=0.3,
    age_factor_cap_days=365,
)
```

## Promotion Workflow

### 1. Candidate Detection

The system scans all domain pages and identifies candidates:

```python
from llm_wiki.promotion.engine import PromotionEngine

engine = PromotionEngine()
candidates = engine.find_candidates()

for candidate in candidates:
    print(f"{candidate.page_id}: score={candidate.promotion_score}")
    print(f"  Cross-domain refs: {candidate.cross_domain_references}")
    print(f"  Referring domains: {candidate.referring_domains}")
```

### 2. Auto-Promotion or Review

Based on configuration:

- **require_approval=False**: Eligible pages are auto-promoted immediately
- **require_approval=True**: Pages are added to the review queue for approval

```python
# Process all candidates
report = engine.process_candidates()

print(f"Auto-promoted: {report.auto_promoted}")
print(f"Suggested for review: {report.suggested_for_review}")
```

### 3. Page Promotion

When a page is promoted:

1. **Copy to shared**: Page is copied to `wiki_system/shared/`
2. **Create tombstone**: Original location gets a redirect marker
3. **Update backlinks**: Backlink index is updated
4. **Log action**: Action is recorded in reports

```python
# Promote a specific page
result = engine.promote_page(
    page_id="distributed-systems",
    source_domain="domain1",
    update_references=True
)

if result.success:
    print(f"Promoted to: {result.shared_location}")
    print(f"References updated: {result.references_updated}")
```

### 4. Un-promotion

Pages can be un-promoted back to domain-local:

```python
result = engine.unpromote_page(
    page_id="distributed-systems",
    target_domain="domain1"
)

if result.success:
    print(f"Un-promoted to: {result.shared_location}")
```

## CLI Commands

### Check for Candidates

```bash
llm-wiki promote check
```

Shows all pages eligible for promotion with scores and cross-domain references.

### Process Promotions

```bash
llm-wiki promote process
```

Automatically promotes eligible pages or adds them to review queue.

### Promote Specific Page

```bash
llm-wiki promote promote test-page --domain domain1
```

Manually promote a specific page.

### Un-promote Page

```bash
llm-wiki promote unpromote test-page --domain domain1
```

Move a shared page back to domain-local.

### Dry-Run Mode

```bash
llm-wiki promote promote test-page --domain domain1 --dry-run
```

Simulates promotion without making changes.

## Integration with Review Queue

When `require_approval=True`, promotion candidates are added to the review queue with:

- **Type**: `ReviewType.PROMOTION`
- **Priority**: `HIGH` if auto-promote threshold, `MEDIUM` otherwise
- **Metadata**: Includes scores, quality, cross-domain references, etc.

```python
from llm_wiki.review.models import ReviewType, ReviewStatus

# Check pending promotions
pending = queue.get_pending_items(item_type=ReviewType.PROMOTION)

for item in pending:
    print(f"Page: {item.target_id}")
    print(f"  Score: {item.metadata['promotion_score']}")
    print(f"  Referring domains: {item.metadata['referring_domains']}")

    # Review and approve
    item.approve("reviewer@example.com", notes="Approved for promotion")
    queue.update_item(item)
```

## Directory Structure

### Shared Space

```
wiki_system/
├── shared/
│   ├── distributed-systems.md
│   ├── security-patterns.md
│   └── ...
├── domains/
│   ├── domain1/
│   │   └── pages/
│   │       ├── domain1-specific.md
│   │       └── [tombstone markers for promoted pages]
│   └── domain2/
│       └── pages/
└── reports/
    ├── promotion_20240414_120000.json
    └── ...
```

### Tombstone Format

When a page is promoted, the original location contains:

```markdown
---
id: distributed-systems
kind: page
title: [Moved to shared]
domain: shared
status: archived
updated_at: 2024-04-14T12:00:00Z
---

This page has been promoted to the shared space and is now at `/shared/distributed-systems.md`.

All references should be updated to point to the shared version.
```

## Reporting

Promotion reports are saved to `wiki_system/reports/promotion_TIMESTAMP.json`:

```json
{
  "timestamp": "2024-04-14T12:00:00+00:00",
  "total_candidates": 15,
  "auto_promoted": 3,
  "suggested_for_review": 5,
  "promotion_results": [
    {
      "page_id": "distributed-systems",
      "success": true,
      "message": "Successfully promoted distributed-systems to shared",
      "shared_location": "wiki_system/shared/distributed-systems.md",
      "references_updated": 5,
      "review_item_id": null
    }
  ]
}
```

## Best Practices

### Quality Control

- Set `min_quality_score` high enough to prevent low-quality content from being promoted
- Review pages before they reach auto-promotion threshold
- Use review queue (`require_approval=True`) for initial rollout

### Cross-Domain References

- Minimum 2 cross-domain references is a good starting point
- Adjust thresholds based on your wiki size and usage patterns
- Monitor referring domains to understand content usage

### Monitoring

- Check promotion reports regularly
- Review the shared space for content organization
- Update backlinks after major reorganizations

## Testing

### Unit Tests

```bash
pytest tests/unit/test_promotion_scorer.py
pytest tests/unit/test_promotion_engine.py
```

### Integration Tests

```bash
pytest tests/integration/test_promotion_workflow.py
```

### Manual Testing

```python
from pathlib import Path
from llm_wiki.promotion.engine import PromotionEngine

# Create test wiki
wiki_base = Path("test_wiki")
engine = PromotionEngine(wiki_base=wiki_base)

# Find candidates
candidates = engine.find_candidates()
print(f"Found {len(candidates)} candidates")

# Promote top candidate
if candidates:
    top = candidates[0]
    result = engine.promote_page(top.page_id, top.domain, dry_run=True)
    print(f"Dry-run: {result.message}")
```

## Troubleshooting

### Pages Not Being Promoted

1. Check page quality score: `llm-wiki govern check`
2. Verify cross-domain references: `llm-wiki promote check`
3. Check promotion configuration in `config/daemon.yaml`
4. Review thresholds: are they too high?

### Review Queue Not Working

1. Verify `review_queue_enabled: true` in daemon config
2. Check review queue directory: `wiki_system/review/`
3. Check for errors in daemon logs

### Performance Issues

- Increase `promotion_every_hours` to run less frequently
- Reduce `min_quality_score` to speed up scoring
- Disable `update_references` for large wikis

## Future Enhancements

1. **Un-promotion Criteria**: Automatically un-promote if cross-domain references drop below threshold
2. **Shared Page Updates**: Notify referencing domains when shared pages change
3. **Conflict Resolution**: Handle cases where same page exists in multiple domains
4. **Custom Scoring**: Allow per-domain or per-page promotion weights
5. **Bulk Operations**: Promote/un-promote groups of related pages
