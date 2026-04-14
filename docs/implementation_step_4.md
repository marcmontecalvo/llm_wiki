# Implementation Step 4 - Daemon governance and exports

## Objective

Make the system self-maintaining enough to be trustworthy.

## Build now

### 1. Daemon scheduler
Add recurring jobs for:
- inbox scan
- retry failed ingests
- lint pages
- rebuild indexes
- detect stale pages
- detect contradictions
- export machine-readable outputs

### 2. Governance checks
Minimum checks:
- schema validity
- orphan pages
- duplicate entities
- stale pages
- low-confidence claims
- source-less claims
- routing mistakes / domain mismatch

### 3. Exports
Implement these first:
- `llms.txt`
- `llms-full.txt`
- page-level JSON sidecars
- simple graph export
- sitemap

### 4. Review flow
Add a lightweight review queue for:
- new shared pages
- low-confidence pages
- conflicting claims
- auto-created entities

## Borrow directly from

### Labhund/llm-wiki
Daemon governance inspiration:
https://github.com/Labhund/llm-wiki

### Pratiyush/llm-wiki
Export targets and machine-readable distribution:
https://github.com/Pratiyush/llm-wiki

### nashsu/llm_wiki
Only later for richer graph UX:
https://github.com/nashsu/llm_wiki

## Deliverable

By the end of Step 4, the system should run on its own in the background, keep itself indexed, and surface things that need human review.
