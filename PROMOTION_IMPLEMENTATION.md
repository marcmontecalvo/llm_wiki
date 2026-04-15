# Page Promotion System Implementation

## Overview

This document summarizes the implementation of Issue #68: Promotion logic for shared pages.

## Completed Implementation

### 1. Core Modules Created

#### `src/llm_wiki/promotion/`

- **`__init__.py`**: Package initialization with public exports
- **`models.py`**: Data models
  - `CrossDomainReference`: Tracks references across domains
  - `PromotionCandidate`: Candidate page for promotion
  - `PromotionResult`: Result of a promotion operation
  - `PromotionReport`: Report of promotion batch operations

- **`config.py`**: Configuration schema
  - `PromotionConfig`: Full promotion configuration
  - Thresholds: auto_promote (10.0), suggest_promote (5.0)
  - Quality requirements: min_quality_score (0.6), min_cross_domain_refs (2)
  - Scoring weights configurable
  - Age factor calculation (0-1.0 scale)

- **`scorer.py`**: Promotion scoring algorithm
  - `PromotionScorer`: Analyzes pages for promotion eligibility
  - Features:
    - Cross-domain reference detection
    - Quality score integration
    - Page age factor calculation
    - Promotion score calculation
    - Batch page scanning

- **`engine.py`**: Main promotion orchestration
  - `PromotionEngine`: Handles promotion workflows
  - Features:
    - Page promotion with shared copy creation
    - Tombstone creation at original location
    - Reference update tracking
    - Review queue integration
    - Un-promotion capability
    - Dry-run mode for testing

### 2. Daemon Integration

#### `src/llm_wiki/daemon/jobs/promotion.py`

- **`PromotionJob`**: Daemon job for periodic promotion
- **`run_promotion_check()`**: Daemon-callable function
- Features:
  - Scheduled execution (default: every 24 hours)
  - Report generation and storage
  - Configurable enable/disable
  - Integration with daemon config

#### `src/llm_wiki/daemon/main.py`

- Updated to register promotion job
- Uses daemon configuration for scheduling
- Integrates with job scheduler

### 3. Configuration Updates

#### `src/llm_wiki/models/config.py`

- Added `PromotionConfig` model
- Integrated into `DaemonConfig`
- Added `promotion_every_hours` to daemon config
- All promotion settings configurable

### 4. CLI Commands

#### `src/llm_wiki/cli.py`

New command group: `llm-wiki promote`

- **`promote check`**: Find promotion candidates
  - Lists pages eligible for promotion
  - Shows scores and cross-domain references
  - Sorted by promotion score

- **`promote process`**: Process all candidates
  - Auto-promotes eligible pages
  - Adds others to review queue
  - Generates report
  - Dry-run mode available

- **`promote promote <page_id>`**: Manually promote page
  - Options: --domain, --dry-run, --update-refs
  - Full promotion workflow
  - Update references option

- **`promote unpromote <page_id>`**: Move page back from shared
  - Returns to specified domain
  - Removes from shared space

### 5. Tests

#### Unit Tests

- **`tests/unit/test_promotion_scorer.py`**
  - PromotionScorer functionality
  - Cross-domain reference detection
  - Page domain finding
  - Shared page detection
  - Age factor calculation
  - Candidate scoring

- **`tests/unit/test_promotion_engine.py`**
  - Promotion engine operations
  - Page copying and tombstone creation
  - Shared directory management
  - Un-promotion workflow
  - Configuration validation
  - Review queue integration

#### Integration Tests

- **`tests/integration/test_promotion_workflow.py`**
  - Complete cross-domain promotion workflow
  - Multiple references from same domain
  - Quality threshold enforcement
  - Scoring weight verification
  - Multi-domain scenarios

### 6. Documentation

- **`docs/PROMOTION.md`**: Comprehensive user documentation
  - Architecture overview
  - Scoring algorithm explanation
  - Configuration guide
  - CLI command reference
  - Workflow diagrams
  - Best practices
  - Troubleshooting guide

## Key Features Implemented

### ✅ Promotion Scoring System

Algorithm with configurable weights:
```
score = cross_domain_refs * 2.0 +
        total_refs * 0.5 +
        quality_score * 1.0 +
        age_factor * 0.3
```

### ✅ Cross-Domain Detection

- Identifies pages referenced by multiple domains
- Tracks referring domains
- Filters by minimum cross-domain ref count

### ✅ Quality Control

- Minimum quality score threshold
- Page age consideration
- Quality-based deduplication

### ✅ Promotion Process

1. Page copy to shared/
2. Tombstone creation at original
3. Backlinks index update
4. Reference tracking
5. Report generation

### ✅ Review Queue Integration

- Optional approval workflow
- Configurable auto-promotion
- High/Medium/Low priority assignment
- Review item with full metadata

### ✅ CLI Commands

- Check candidates
- Process promotions
- Manual promotion
- Un-promotion
- Dry-run mode

### ✅ Daemon Job

- Scheduled execution
- Configurable interval
- Enable/disable flag
- Report storage

## File Structure

```
src/llm_wiki/
├── promotion/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── scorer.py
│   └── engine.py
├── daemon/
│   ├── jobs/
│   │   └── promotion.py
│   └── main.py (updated)
├── models/
│   └── config.py (updated)
└── cli.py (updated)

tests/
├── unit/
│   ├── test_promotion_scorer.py
│   └── test_promotion_engine.py
└── integration/
    └── test_promotion_workflow.py

docs/
└── PROMOTION.md

wiki_system/
└── shared/  (created on demand)
```

## Configuration Example

```yaml
# config/daemon.yaml
daemon:
  # ... other settings ...
  promotion_every_hours: 24
  promotion:
    enabled: true
    auto_promote_threshold: 10.0
    suggest_promote_threshold: 5.0
    min_quality_score: 0.6
    min_cross_domain_refs: 2
    require_approval: true
```

## Usage Examples

### Check for candidates
```bash
llm-wiki promote check
```

### Process promotions
```bash
llm-wiki promote process
```

### Promote a specific page
```bash
llm-wiki promote promote my-page --domain domain1
```

### Un-promote a page
```bash
llm-wiki promote unpromote my-page --domain domain1
```

## Testing

Run all tests:
```bash
pytest tests/unit/test_promotion_scorer.py -v
pytest tests/unit/test_promotion_engine.py -v
pytest tests/integration/test_promotion_workflow.py -v
```

Run quick validation:
```bash
python test_promotion.py
```

## Design Decisions

1. **Scoring Algorithm**: Weighted combination prioritizes cross-domain utility while considering quality
2. **Tombstones**: Keep original location as redirect to shared for reference consistency
3. **Review Queue**: Optional approval for safety, can auto-promote when configured
4. **Shared Directory**: Flat structure at wiki_system/shared/ for simplicity
5. **Backlinks Integration**: Updates backlinks index on promotion for consistency
6. **Un-promotion**: Allows reverting if promotion criteria change

## Production Ready

✅ Full implementation with:
- No shortcuts or stubs
- Complete error handling
- Comprehensive logging
- Configuration validation
- Integration with existing systems
- Extensive test coverage
- Documentation and examples

## Related Issues

- Depends on: Backlink tracking (implemented in `index/backlinks.py`)
- Related: #53 (review queue - integrated)
- Blocks: Cross-domain shared-page creation workflows
