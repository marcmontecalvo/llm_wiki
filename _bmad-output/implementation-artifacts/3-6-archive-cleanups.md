---
title: "Story 3-6 Follow-on Cleanups"
description: "Actionable follow-ups from adversarial code review of archive lifecycle implementation"
created: 2026-05-22
---

# Story 3-6 Code Review Findings — To Clean Up

These were identified during the adversarial review of story 3-6 (Topic Archive Lifecycle)
and confirmed as non-blocking but worthwhile to address later.

## A1. MCP tools missing archive operations

**Severity:** Medium
**Location:** `src/llm_wiki/mcp/tools.py`

The MCP server has 7 tools (query, ingest, ingest_status, search, read_page, list_pages, export, domain_dashboard) but none expose archive operations. The REST endpoint exists at `GET /v1/domains/{domain}/archive` and CLI commands exist (`govern archive`, `govern unarchive`), but MCP clients have no way to list, archive, or unarchive pages programmatically.

**Why:** MCP tools follow the same pattern as REST routes, and archive endpoints were added after the MCP tools were already registered.

**How to apply:** Add MCP tools for `list_archive`, `archive_page`, and `unarchive_page` following the existing register_tools pattern. Mirror the archive router and service functions.

## A2. WikiQuery has no unified archive facade

**Severity:** Low
**Location:** `src/llm_wiki/query/search.py`

Archive logic is scattered across multiple methods:
- `_scan_archived_pages()` — filesystem scan for archived pages (search.py:261)
- `include_archived` parameter on `search()`, `list_pages()`, and `get_page()`
- Archive filter logic (`if not include_archived and metadata.get("archived")`) duplicated conceptually across search/list_pages

There's no single `WikiQuery.is_archived(page_id)` or `WikiQuery.archive_operations` property that encapsulates the archive state. Consumers have to know about `include_archived` parameters and manual domain scoping.

**Why:** Archive operations grew organically across the codebase rather than being encapsulated behind a dedicated interface.

**How to apply:** Add a `WikiArchive` helper class or `WikiQuery.archive` property with methods like `is_archived(page_id)`, `list_archived(domain)`, and convenience for the `include_archived` toggle.

## A3. `read_page` MCP tool doesn't check archive directory

**Severity:** Low
**Location:** `src/llm_wiki/mcp/tools.py:350-377`

The `read_page` MCP tool resolves content from `wiki_base / "domains" / domain / "pages/"` and `wiki_base / "shared/"` but does NOT check the `archive/` directory. If a page has been archived, `wiki.get_page()` falls back to archive and returns it, but the content fetched afterward will be empty (no file found in pages/ or shared/). This means archived pages returned by MCP `read_page` will have empty content.

**Why:** MCP read_page walks its own file paths instead of reusing the REST router's read_page logic which correctly reads from the resolved file path.

**How to apply:** Update `read_page` MCP tool to check `archive/` directories when `page_file` is not found in `pages/`, using the domain from `page.get("domain", "general")`.

## A4. Merged entry title extraction in GRAPH.md

**Severity:** Informational
**Location:** `src/llm_wiki/query/graph.py`

The `generate_entry` method extracts the "merged" title from the LLM response text using a fragile regex pattern:
```python
title = str(match.group(1)).strip() if match else ""
```

This relies on the LLM output format being consistent. If the LLM doesn't include the exact `merged: <title>` pattern, the entry will have an empty title.

**Why:** The pattern matches a specific LLM output format that may vary across models or prompt iterations.

**How to apply:** Add a fallback: if merged title is empty, use the best individual title from the entries list. Or add structured output enforcement (pydantic model) to the synthesis call.

## A5. No `include_archived` support in MCP query tool

**Severity:** Low
**Location:** `src/llm_wiki/mcp/tools.py:203-249`

The MCP `query` tool does not accept `include_archived` parameter, unlike the REST endpoint. This means MCP clients always get archived-pages-stripped results with no way to opt in.

**Why:** The MCP query tool predates the archive feature.

**How to apply:** Add `include_archived: bool | None = None` parameter to the MCP `query` tool and pass it through to `wiki.search()`. Same for MCP `search` tool.

## A6. grep/fzf utility script references stale file path

**Severity:** Informational
**Location:** Project utilities (if they exist)

Any grep/fzf script or shell alias that references `wiki_system/` paths (the old directory name) instead of the current `wiki_base` config path would fail. The codebase migrated from `wiki_system/` to configurable `wiki_base`, but shell convenience scripts may still reference the old path.

**Why:** The wiki base path became configurable but shell tooling wasn't updated.

**How to apply:** Search for hardcoded `wiki_system` references in shell scripts,Makefiles, or dotfiles and update to use the configured path.
