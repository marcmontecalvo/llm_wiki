# ADR 002: Page ID Generation Strategy

**Status**: Accepted
**Date**: 2026-04-13
**Deciders**: Implementation Team

## Context

Wiki pages need stable, unique identifiers that:
- Enable reliable cross-references between pages
- Support URL routing
- Remain human-readable for debugging and manual inspection
- Work across all page types (pages, entities, concepts, sources)
- Handle potential ID collisions gracefully

## Decision

We will use **slug-based IDs** generated from page titles/names with the following characteristics:

### ID Format
- **Slugification**: Convert titles to lowercase, replace non-alphanumeric characters with hyphens
- **URL-safe**: Only lowercase letters (a-z), numbers (0-9), and hyphens (-)
- **Unicode normalization**: Convert accented characters to ASCII equivalents (e.g., "café" → "cafe")
- **Length limit**: 100 characters maximum (configurable)
- **Deterministic**: Same input always produces same ID (no timestamps, UUIDs, etc.)

### Optional Prefixes
- **Domain prefix**: `{domain}-{title-slug}` (e.g., "homelab-docker-compose")
- **Entity type prefix**: `{entity_type}-{name-slug}` (e.g., "person-john-doe")
- Prefixes are opt-in and may be omitted if they exceed length limits

### Collision Handling
- **Counter suffix**: Append "-2", "-3", etc. for duplicate IDs
- **Caller responsibility**: Application code provides collision detection function
- **Safety limit**: Fail after 1000 collision attempts to prevent infinite loops

### Implementation
- Core function: `generate_page_id(title, domain=None, collision_check=None, max_length=100)`
- Specialized helpers: `generate_entity_id()`, `generate_concept_id()`
- Pure functions with no side effects (no database queries, no file I/O)

## Rationale

### Why Slug-Based IDs?

**Human readability**: Developers and users can understand what a page is about from its ID
- ✅ `machine-learning-basics` (readable)
- ❌ `f3a8b2c9-4d6e-11ed-bdc3-0242ac120002` (opaque UUID)
- ❌ `page_1678234567` (meaningless number)

**URL friendliness**: IDs can be used directly in URLs without encoding
- `https://wiki.example.com/pages/machine-learning-basics`

**Debugging**: Easier to identify pages in logs, error messages, and database queries

**Predictability**: Same title always generates same ID (useful for testing and migrations)

### Why Not Other Approaches?

**UUIDs**:
- ❌ Not human-readable
- ❌ Harder to remember/communicate
- ✅ Guaranteed uniqueness (but we handle collisions anyway)

**Auto-increment IDs**:
- ❌ Not portable across instances
- ❌ No semantic meaning
- ❌ Requires database/state

**Hash-based IDs**:
- ❌ Still opaque (e.g., "a3f8b2c9")
- ❌ Potential for collisions without full hash
- ✅ Deterministic (but so are slugs)

**Title as-is**:
- ❌ Not URL-safe (spaces, special characters)
- ❌ Case sensitivity issues
- ❌ Length issues

### Design Choices

**Deterministic generation**: Enables testing, idempotent operations, and predictable behavior

**Caller-provided collision detection**:
- Keeps ID generation pure (no side effects)
- Allows different storage backends (in-memory, database, filesystem)
- Testable without mocking

**Length limits**:
- Prevents database field overflow
- Ensures URLs stay reasonable
- Truncation preserves most significant words (beginning of title)

**Unicode normalization**:
- Ensures ASCII-only output for maximum compatibility
- Prevents duplicate IDs from "café" and "cafe"
- May lose some semantic meaning (acceptable tradeoff)

## Consequences

### Positive
- ✅ Human-readable IDs improve developer experience
- ✅ URL-safe format works everywhere
- ✅ Deterministic generation simplifies testing
- ✅ Pure functions are easy to test and reason about
- ✅ Collision handling prevents duplicates

### Negative
- ❌ Title changes require ID migration (or accepting stale IDs)
- ❌ Non-English titles may lose meaning after normalization
- ❌ Long titles get truncated (may lose specificity)
- ❌ Similar titles create similar IDs (e.g., "Test" → "test", "Test!" → "test")

### Neutral
- ⚠️ Collision detection is caller responsibility (requires discipline)
- ⚠️ Domain/type prefixes are optional (inconsistent usage possible)

## Mitigation Strategies

**Title changes**:
- Document that IDs are stable once created (don't regenerate)
- Future: Add ID alias/redirect support if needed

**Non-English content**:
- Unicode normalization is best-effort
- Future: Could support language-specific transliteration

**Truncation**:
- 100 character limit is generous for most cases
- Future: Could preserve keywords using NLP techniques

**Collision frequency**:
- Minimize through good titling conventions
- Monitor collision rates in production
- Counter suffix maintains uniqueness

## Examples

```python
# Basic usage
generate_page_id("Machine Learning Basics")
# → "machine-learning-basics"

# With domain prefix
generate_page_id("Docker Compose", domain="homelab")
# → "homelab-docker-compose"

# With collision detection
def check_exists(page_id: str) -> bool:
    return page_id in existing_page_ids

generate_page_id("Python", collision_check=check_exists)
# → "python" (if new) or "python-2" (if exists)

# Entity IDs
generate_entity_id("Apple Inc.", entity_type="company")
# → "company-apple-inc"

# Concept IDs
generate_concept_id("Artificial Intelligence")
# → "artificial-intelligence"
```

## Alternatives Considered

### 1. Content-based hashing
Generate IDs from hash of page content (e.g., first 8 chars of SHA-256).

**Rejected**: Not human-readable, content changes would change ID.

### 2. Semantic IDs with versioning
Include semantic version in ID (e.g., "python-v1", "python-v2").

**Rejected**: Adds complexity, unclear when to increment version.

### 3. Hierarchical IDs
Include parent category in ID (e.g., "programming/languages/python").

**Rejected**: Creates coupling between pages, limits reorganization flexibility.

## References

- URL slug best practices: https://moz.com/learn/seo/url
- Unicode normalization: https://unicode.org/reports/tr15/
- Django slugify implementation (inspiration): https://github.com/django/django/blob/main/django/utils/text.py
