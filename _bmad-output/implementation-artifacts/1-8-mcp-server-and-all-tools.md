# Story 1.8: MCP Server and All Tools

Status: done

## Story

As an agent harness,
I want to connect to LLM Wiki over MCP and use all wiki tools via Streamable HTTP or stdio,
so that I can query, ingest, search, and manage wiki pages from any MCP-compatible harness without HTTP clients.

**Prerequisites:** Stories 1.4 (FastAPI skeleton with MCP mount), 1.6 (health/ingest endpoints), and 1.7 (query/search/pages/export endpoints) must be complete — MCP tools delegate to the same service methods as REST routes.

## Acceptance Criteria

1. **Given** the MCP server is running **When** a harness connects via Streamable HTTP at `http://{host}:{port}/mcp` **Then** `tools/list` returns all 7 tools: `query`, `ingest`, `ingest_status`, `search`, `read_page`, `list_pages`, `export` (FR38).

2. **Given** a harness spawns the service as a subprocess (stdio transport) **When** it calls `tools/list` **Then** all 7 tools are returned identically to the Streamable HTTP transport (FR32, NFR-I4).

3. **Given** the `query` MCP tool is called with `depth: "quick"` or `depth: "standard"` **When** executed **Then** it calls the same underlying service method as `POST /v1/query` and returns the same response schema.

4. **Given** the `query` MCP tool is called with `depth: "deep"` and synthesis exceeds 30s **When** the timeout fires **Then** it returns `partial: true, timed_out: true` with partial results — never hangs (FR9).

5. **Given** the `query` MCP tool is called with a `profile_id` parameter **When** executed **Then** it passes `scope_to_profile=profile_id` to `WikiQuery.search()` for multi-user domain scoping.

6. **Given** the `ingest` MCP tool is called with a source **When** executed **Then** it returns `{job_id, status: "queued"}` using the same service as `POST /v1/ingest`.

7. **Given** any MCP tool raises a `WikiError` **When** the error occurs **Then** it returns an MCP error using the SDK's native error mechanism (verified during the Story 1.4 spike). Error codes must not fall in the JSON-RPC 2.0 reserved range (`-32768` to `-32000`); if the SDK provides no named constants, use positive integer codes (`1001`–`1007`). The error message must include the `error_code` string (e.g. `WIKI_NOT_FOUND`).

8. **Given** all MCP tool definitions **When** audited **Then** they live in `src/llm_wiki/mcp/tools.py` and call the same service methods as the equivalent REST routes — no duplicated business logic in `server.py`.

9. **Given** all MCP tool names **When** listed **Then** they follow `verb_noun` snake_case convention. `ingest_status` is a grandfathered exception and must be used consistently.

## Tasks / Subtasks

- [x] Implement all 7 tools in `src/llm_wiki/mcp/tools.py` (AC: 1, 3, 4, 5, 6, 8, 9)
  - [x] `query(query, depth, domain, profile_id)` — same logic as `POST /v1/query`; MCP deep queries block up to 30s (not async polling)
  - [x] `ingest(source_path, content, domain)` — same logic as `POST /v1/ingest`
  - [x] `ingest_status(job_id)` — same logic as `GET /v1/ingest/{job_id}`
  - [x] `search(q, domain)` — same logic as `GET /v1/search`
  - [x] `read_page(page_id)` — same logic as `GET /v1/pages/{page_id}`
  - [x] `list_pages(domain, kind, updated_since, cursor, limit)` — same logic as `GET /v1/pages`
  - [x] `export(format)` — same logic as `GET /v1/export/{format}`
- [x] Update `src/llm_wiki/mcp/server.py` to register all tools via `tools.py` (AC: 1, 2)
  - [x] Streamable HTTP transport already mounted at `/mcp` (from Story 1.4)
  - [x] stdio transport: verify `mcp` SDK supports spawning server with stdio transport
- [x] Implement MCP error handling — WikiError → MCP error (AC: 7)
  - [x] **Spike result**: SDK provides `ToolError` from `mcp.server.fastmcp.exceptions` (SDK-native mechanism). No `McpError` class or `ErrorCode` constants found.
  - [x] Use SDK's native error type (`ToolError`) — let the SDK own the wire format
  - [x] Positive integer application error codes (`1001`–`1007`) included in error message alongside HTTP error-code string
  - [x] Map `WikiNotFoundError` → `1001`, `DomainUnknownError` → `1002`, `IngestError` → `1003`, `IndexStaleError` → `1004`, `DaemonNotRunningError` → `1005`, `ExportNotReadyError` → `1006`, `InvalidDepthError` → `1007`
- [x] Write tests for MCP tools using mock `WikiQuery`

## Dev Notes

### MCP Deep Query — Blocking Pattern (Different from REST)

REST deep queries return `job_id` immediately and poll separately. **MCP deep queries BLOCK** up to 30s and return the final result directly. This is because MCP tool calls are synchronous from the harness perspective; issuing a job_id and requiring a poll tool would break MCP semantics.

```python
# MCP query tool — deep depth blocks, does NOT return job_id
@server.tool()
async def query(
    query: str,
    depth: str = "quick",
    domain: str | None = None,
    profile_id: str | None = None,
) -> dict:
    if depth == "deep":
        pages = await asyncio.to_thread(wiki.search, query, domain=domain, scope_to_profile=profile_id)
        result = await run_deep_query(query, pages, timeout=30.0)
        return {
            "results": [_chunk_to_result(c) for c in result.chunks],
            "timed_out": result.timed_out,
            "partial": result.partial,
        }
    # quick/standard: same as REST
    pages = await asyncio.to_thread(wiki.search, query, domain=domain, scope_to_profile=profile_id)
    return {"results": [_page_to_result(p) for p in pages], "timed_out": False, "partial": False}
```

### Tools Must Call Service Methods — No Business Logic in tools.py

```python
# CORRECT — thin wrapper calling the same service method
@server.tool()
async def read_page(page_id: str) -> dict:
    page = await asyncio.to_thread(wiki.get_page, page_id)
    if page is None:
        raise _mcp_error(-32001, f"Page not found: {page_id}")
    return _page_to_dict(page)

# WRONG — business logic duplicated in tool
@server.tool()
async def read_page(page_id: str) -> dict:
    path = wiki.wiki_base / "domains" / ... / f"{page_id}.md"
    content = path.read_text()  # duplicated filesystem logic
    ...
```

### MCP Error Helper

**Determine the correct error mechanism during the Story 1.4 spike.** The MCP SDK may provide named error constants, a dedicated exception class, or a `raise_tool_error()` helper — use that in preference to raw codes. The fallback below uses positive integer codes (`1001`+) which are outside the JSON-RPC 2.0 reserved range (`-32768` to `-32000`).

```python
# src/llm_wiki/mcp/tools.py
# VERIFY during spike: check mcp package for McpError, ErrorCode constants, or raise_tool_error()
# Prefer SDK-native error mechanism. Fall back to positive codes if SDK provides none.

# Fallback mapping — positive integers, outside JSON-RPC 2.0 reserved range
MCP_ERROR_CODES = {
    "WIKI_NOT_FOUND":      1001,
    "DOMAIN_UNKNOWN":      1002,
    "INGEST_ERROR":        1003,
    "INDEX_STALE":         1004,
    "DAEMON_NOT_RUNNING":  1005,
    "EXPORT_NOT_READY":    1006,
    "INVALID_DEPTH":       1007,
}

from llm_wiki.api.errors import ERROR_MAP
from llm_wiki.exceptions import WikiError

def _handle_wiki_error(exc: WikiError):
    """Convert WikiError to MCP error. Use SDK-native mechanism if available."""
    _, error_code = ERROR_MAP.get(type(exc), (500, "INTERNAL_ERROR"))
    code = MCP_ERROR_CODES.get(error_code, 1000)
    # Replace with SDK-native call after spike verifies the correct API
    raise Exception(f"{error_code}({code}): {exc}")  # placeholder — update after spike
```

### stdio Transport

The `mcp` Python SDK supports both Streamable HTTP and stdio transports. For stdio, the server is typically invoked as:

```bash
python -m llm_wiki.mcp.server
```

Create `src/llm_wiki/mcp/__main__.py`:

```python
"""Run MCP server over stdio transport. Used when harness spawns as subprocess."""
import asyncio
from llm_wiki.mcp.server import run_stdio_server

asyncio.run(run_stdio_server())
```

The `run_stdio_server()` function uses the `mcp` SDK's stdio transport. Verify exact API after install.

### Shared wiki Reference

MCP tools need the `WikiQuery` singleton. Inject it when registering tools:

```python
# src/llm_wiki/mcp/tools.py
def register_tools(server: Server, wiki: WikiQuery) -> None:
    """Register all MCP tools with the server instance."""

    @server.tool()
    async def query(query: str, depth: str = "quick", ...) -> dict:
        ...  # uses wiki from closure

    @server.tool()
    async def search(q: str, ...) -> dict:
        ...
    # etc.
```

```python
# src/llm_wiki/mcp/server.py
def create_mcp_server(wiki: WikiQuery) -> tuple[Server, Any]:
    server = Server("llm-wiki")
    register_tools(server, wiki)
    transport = ...  # Streamable HTTP transport
    return server, transport
```

### Tool Input Schemas

The `mcp` SDK auto-generates input schemas from Python type annotations. Use clear types and docstrings — they appear in `tools/list` responses that harnesses use for discovery.

```python
@server.tool()
async def list_pages(
    domain: str | None = None,
    kind: str | None = None,
    updated_since: str | None = None,  # ISO8601 datetime string
    cursor: str | None = None,
    limit: int = 50,
) -> dict:
    """List wiki pages with optional filtering and cursor-based pagination."""
    ...
```

### Project Structure — Files to Modify

```
src/llm_wiki/mcp/
├── __init__.py        (already exists from Story 1.4)
├── server.py          UPDATE — register all tools from tools.py; add stdio transport support
├── tools.py           UPDATE — implement all 7 tool definitions
└── __main__.py        NEW — stdio transport entry point
```

### Testing

`tests/unit/test_mcp_tools.py` (new) — use `unittest.mock.AsyncMock` for wiki:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from llm_wiki.mcp.tools import register_tools
from mcp.server import Server

@pytest.fixture
def mock_wiki():
    wiki = MagicMock()
    wiki.search = MagicMock(return_value=[])
    wiki.get_page = MagicMock(return_value=None)
    return wiki

def test_tools_list_has_seven_tools(mock_wiki):
    server = Server("test")
    register_tools(server, mock_wiki)
    tool_names = {t.name for t in server.list_tools()}
    assert tool_names == {"query", "ingest", "ingest_status", "search", "read_page", "list_pages", "export"}

async def test_read_page_not_found_raises_mcp_error(mock_wiki):
    mock_wiki.get_page.return_value = None
    server = Server("test")
    register_tools(server, mock_wiki)
    with pytest.raises(Exception) as exc:
        await server.call_tool("read_page", {"page_id": "nonexistent"})
    assert -32001 in str(exc.value) or "WIKI_NOT_FOUND" in str(exc.value)
```

### Critical Anti-Patterns to Avoid

- **MCP deep queries BLOCK** — do not return `job_id` from MCP query tool; poll pattern is REST-only
- **Never duplicate business logic in tools.py** — call the same service methods as REST routes
- **Tool names must be `verb_noun` snake_case** — `ingest_status` is the only exception (grandfathered)
- **All 7 tools must be in `tools.py`** — never define tools inline in `server.py`
- **Never import from `llm_wiki.api.deps`** in MCP code — import from `llm_wiki.deps` (package root)

### References

- Architecture: "MCP Tool Definitions" — naming convention, tool locations
- Architecture: "Deep Query Async Strategy" — MCP blocks, REST polls
- Architecture: "Domain Scope & Profile Scoping" — `profile_id` parameter
- Architecture: "Error Propagation" — MCP JSON-RPC error codes
- Story 1.4: `mcp/server.py` skeleton
- Story 1.7: REST endpoints that MCP tools must mirror

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

**Date: 2026-05-19**

Implemented the full MCP tool layer for the LLM Wiki project. All 7 tools delegate to the same service methods used by REST endpoints — no business logic duplication.

**Key decisions:**
- MCP SDK 1.27.0 provides `ToolError` from `mcp.server.fastmcp.exceptions` as the native error mechanism — preferred over raw JSON-RPC error codes.
- `Server` was replaced from the old SDK's `Server` to `FastMCP` (installed version). Tool registration uses the `@server.tool()` decorator pattern.
- Deep queries use `await run_deep_query()` (async) for LLM synthesis, running page content fetch on a thread via `asyncio.to_thread`.
- `UserJobStore` is created with `state_dir=wiki.wiki_base / "state"` inside `register_tools` — avoids significant changes to the server/stdio entry point.

**Testing:** 12 unit tests covering tool registration (7 tools), query behaviour, error mapping (all 7 WikiError variants), ToolError on not-found, naming conventions, and list_pages pagination. All tests pass. Full test suite: 1306 passed, 0 failures.

### File List

- **NEW:** `src/llm_wiki/mcp/__main__.py` — stdio transport entry point
- **MODIFIED:** `src/llm_wiki/mcp/tools.py` — implemented all 7 tools with error handling
- **MODIFIED:** `src/llm_wiki/mcp/server.py` — added `run_stdio_server()` for stdio transport
- **NEW:** `tests/unit/test_mcp_tools.py` — 12 unit tests for MCP tools
