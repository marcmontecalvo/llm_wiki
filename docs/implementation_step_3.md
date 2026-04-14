# Implementation Step 3 - Extraction, integration, and indexing

## Objective

Turn normalized documents into durable wiki state.

## Build now

### 1. Extraction pass
The model should extract only structured outputs:
- entities
n- concepts
- claims
- relationships
- candidate destination pages
- confidence values

Do not let the model freely draft final pages yet.

### 2. Integration pass
Integration should be deterministic enough to re-run.

Flow:
1. read normalized source
2. read extracted JSON
3. identify existing target pages
4. merge additive facts
5. append citations/source refs
6. update backlinks/indexes
7. log the diff

### 3. Shared vs domain-local logic
Default:
- write into domain-local pages first

Promote to shared only when:
- the same concept/entity appears across multiple domains
- the concept is clearly general-purpose
- the promotion score crosses threshold

### 4. Indexes
Build at least three indexes:
- metadata index
- fulltext index
- graph edge index

## Borrow directly from

### Labhund/llm-wiki
Pipeline mentality, maintenance loop, query/index separation:
https://github.com/Labhund/llm-wiki

### NVK
Scoped wiki/project conventions:
https://github.com/nvk/llm-wiki

### kenhuangus/llm-wiki
Only for metrics/eval ideas, not architecture:
https://github.com/kenhuangus/llm-wiki

## Hard rules

- no silent page rewrites
- every integration writes a change log
- every claim should preserve source reference
- shared pages are opt-in, not the default dumping ground

## Deliverable

By the end of Step 3, the system should be able to ingest a source and update the right wiki pages plus indexes without manual editing.
