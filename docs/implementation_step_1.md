# Implementation Step 1 - Foundation and contracts

## Objective

Create the repo skeleton and define the contracts before writing real logic.

## Build now

### 1. Folder structure
Implement the folder structure already laid out in `README.md`.

### 2. Config files
Create these first:
- `config/domains.yaml`
- `config/daemon.yaml`
- `config/routing.yaml`
- `config/models.yaml`

### 3. Core schemas
Define strict schemas for:
- source document metadata
- extracted entities
- extracted claims
- domain routing decision
- integration result
- page frontmatter
- review state

Use JSON Schema or Pydantic. No loose dict soup.

### 4. Stable page templates
Create base templates for:
- source pages
- concept pages
- entity pages
- synthesis pages
- domain index pages

### 5. Logging contract
Add append-only logs for:
- ingest attempts
- routing decisions
- integration changes
- review findings
- daemon errors

## Hard rules

- No model writes directly into arbitrary paths.
- All model output must pass schema validation.
- All pages need frontmatter.
- Every page must belong to exactly one of: `domain`, `shared`, `system`.

## Steal from

- Labhund: daemon + pipeline shape
  https://github.com/Labhund/llm-wiki
- NVK: topic/project scoping
  https://github.com/nvk/llm-wiki
- Pratiyush: sidecar/export discipline
  https://github.com/Pratiyush/llm-wiki

## Deliverable

At the end of Step 1, the repo should still be mostly scaffolding, but the structure should be locked enough that later code does not thrash it.
