# Story 3.5: Per-Domain Dashboards

Status: backlog

## Story

As an operator,
I want per-domain health dashboards summarizing page count, confidence distribution, and recent changes,
So that I can assess the quality and activity of each knowledge domain at a glance without querying individual pages.

**FR:** FR49
**Dependencies:** None — reads from index structures already built by Epic 1

## Acceptance Criteria

1. **Given** `GET /v1/domains/{domain}/dashboard` **When** called for a configured domain **Then** it returns: `page_count`, `confidence_distribution` (histogram buckets: 0–0.3, 0.3–0.6, 0.6–1.0), `recent_changes` (last 10 page mutations from changelog), `low_confidence_count`, `stale_count`, `last_governance_run`.

2. **Given** `GET /v1/domains/{domain}/dashboard` for an unknown domain **When** called **Then** it returns HTTP 404 `DOMAIN_UNKNOWN`.

3. **Given** the dashboard endpoint **When** called **Then** it responds within 500ms — data is computed from in-memory index state, not a full filesystem scan.

4. **Given** the MCP server **When** updated for this story **Then** a `domain_dashboard` tool is added that calls the same service method as the REST endpoint.

5. **Given** `llm-wiki govern dashboard [--domain <name>] [--json]` **When** run **Then** it prints the dashboard for the specified domain (or all domains if omitted), with `--json` emitting machine-parseable output (NFR-I3).

6. **Given** the dashboard data **When** generated **Then** it is derived from existing index files (metadata, backlinks, changelog) — no new persistent state is introduced for dashboards.

## Tasks / Subtasks

- [ ] Task 1: Create dashboard service endpoint (AC: 1, 2, 3)
  - [ ] 1.1 New file: `src/llm_wiki/api/routers/dashboard.py` — REST endpoint `GET /v1/domains/{domain}/dashboard`
  - [ ] 1.2 Create `get_domain_dashboard(domain: str, wiki_root: Path) -> DashboardResponse` service function
  - [ ] 1.3 `page_count`: count pages in domain directory from metadata index
  - [ ] [ ] 1.4 `confidence_distribution`: histogram `{"0.0-0.3": count, "0.3-0.6": count, "0.6-1.0": count}` from metadata index confidence scores
  - [ ] 1.5 `recent_changes`: last 10 entries from `changelog/log.py` (append-only changelog)
  - [ ] 1.6 `low_confidence_count`: count pages with `confidence_score < 0.4`
  - [ ] 1.7 `stale_count`: count pages with `updated_at` older than `staleness_threshold_days` for domain
  - [ ] 1.8 `last_governance_run`: read from `state/jobs.json` for the last GovernanceJob completion
  - [ ] 1.9 Unknown domain returns 404 `DOMAIN_UNKNOWN` from error handler in `api/errors.py`
- [ ] Task 2: Create response models (AC: 1)
  - [ ] 2.1 New file: `src/llm_wiki/api/models/dashboard.py` — Pydantic models for dashboard response
  - [ ] 2.2 `DashboardResponse` model matching AC:1 structure exactly
  - [ ] 2.3 `DashboardListResponse` for listing all domains — used by CLI when no domain specified
- [ ] Task 3: Add MCP tool (AC: 4)
  - [ ] 3.1 Add `domain_dashboard` tool to `src/llm_wiki/mcp/tools.py`
  - [ ] 3.2 Tool delegates to same service function as REST endpoint — no code duplication
  - [ ] 3.3 Tool signature: `domain_dashboard(domain: str) -> dict`
- [ ] Task 4: Add CLI command (AC: 5)
  - [ ] 4.1 Add `govern dashboard` subcommand to `src/llm_wiki/cli.py` under existing `govern` group
  - [ ] 4.2 Options: `--domain <name>`, `--json`
  - [ ] 4.3 Without `--domain`: iterates all configured domains, prints formatted table
  - [ ] 4.4 With `--domain`: prints selected domain dashboard
  - [ ] 4.5 Formatting: aligned columns, human-readable confidence histogram bars (simple text)
- [ ] Task 5: Write tests (AC: 1, 2, 5)
  - [ ] 5.1 Unit: test `get_domain_dashboard()` with known page set — verify counts
  - [ ] 5.2 Unit: test confidence distribution buckets with edge cases (exactly 0.3, exactly 0.6)
  - [ ] 5.3 Unit: test unknown domain returns correct error code
  - [ ] 5.4 Unit: test changelog parsing (last 10 entries)
  - [ ] 5.5 Integration: test full REST response body content
  - [ ] 5.6 Integration: test MCP tool response matches REST
  - [ ] 5.7 Integration: test CLI command output format

## Dev Notes

### Key Files to Touch
- `src/llm_wiki/api/routers/dashboard.py` — NEW: REST endpoint and service function
- `src/llm_wiki/api/models/dashboard.py` — NEW: Pydantic response models
- `src/llm_wiki/mcp/tools.py` — UPDATE: add `domain_dashboard` tool registration
- `src/llm_wiki/cli.py` — UPDATE: add `govern dashboard` command
- `src/llm_wiki/api/routers/__init__.py` — UPDATE: register dashboard router
- `tests/unit/test_dashboard.py` — NEW

### Architecture Alignment
- Dashboard data is **derived** — it reads from existing structures (metadata index, changelog, jobs log) and never writes new persistent state
- This is a read-only endpoint — no cache layer, no persistence, computed on-demand from live indexes
- MCP tool is registered in the same pattern as other domain-tied tools (e.g., `search`, `query`)
- CLI follows existing `govern` subcommand convention (e.g., `govern status`, `govern report`)

### Data Sources (all existing)
- `page_count`: Metadata index domain grouping (or direct directory count if index lacks domain filter)
- `confidence_distribution`: Metadata index confidence scores (from Epic 2 trust tagging)
- `recent_changes`: Changelog log file (from Story 1.12 / existing changelog module)
- `low_confidence_count`: Computed from confidence scores
- `stale_count`: Computed from page `updated_at` vs `staleness_threshold_days` in domain config
- `last_governance_run`: `state/jobs.json` GovernanceJob entry

### What NOT to change
- **No new persistent state** — dashboards are always computed, not stored
- **No cache layer** — 500ms target means we don't need caching
- **No changes to index files** — read-only access to existing structures
- **No LLM calls** — entirely algorithmic dashboard computation

### Testing Strategy
- Unit test dashboard computation with controlled mock index data
- Test confidence histogram with boundary values (0.3, 0.6)
- Test changelog parsing — ensure last 10 entries are correct
- Test 404 for unknown domain matches error handler pattern
- Integration test REST response, MCP tool, and CLI output formatting

### Critical Anti-Patterns to Avoid
- **Never scan filesystem during dashboard computation** — use index state or changelog, always
- **Never synchronously scan large directories** — this endpoint must respond in < 500ms
- **Never duplicate the service function** — REST and MCP both call the same function
- **Never format JSON in CLI command** — use the same Pydantic model for both REST and CLI

## References

- FR49 (per-domain dashboards)
- NFR-I3 (CLI --json flag convention)
- Architecture: changelog module patterns
- Architecture: `state/jobs.json` for job status
