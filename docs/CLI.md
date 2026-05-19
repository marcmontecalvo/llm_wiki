# CLI Reference

Command-line interface for the LLM wiki system.

## Installation

```bash
# Install with uv
uv sync

# Verify installation
uv run llm-wiki --version
```

## Commands

### `llm-wiki init`

Initialize a new wiki instance.

```bash
llm-wiki init [--wiki-base PATH]
```

**Options:**
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
uv run llm-wiki init
```

Creates directory structure based on `config/domains.yaml`.

---

### `llm-wiki daemon`

Start the wiki daemon, or manage daemon jobs.

```bash
llm-wiki daemon [SUBCOMMAND] [OPTIONS]
```

**Subcommands:**
- `start` — Start the wiki daemon (explicit form)
- `status` — Show daemon status and recent job execution summary
- `jobs` — Inspect and manage individual daemon jobs

**Options:**
- `--config-dir`: Path to configuration directory (default: `config`)

**Example:**
```bash
# Start daemon (default)
uv run llm-wiki daemon

# Start explicitly
uv run llm-wiki daemon start

# Check status
uv run llm-wiki daemon status
```

**Note:** The daemon runs continuously. Use Ctrl+C to stop.

---

### `llm-wiki search query`

Search wiki content with optional filters.

```bash
llm-wiki search query [QUERY_TEXT] [OPTIONS]
```

**Arguments:**
- `QUERY_TEXT`: Search query (optional if using filters only)

**Options:**
- `--domain`: Filter by domain
- `--kind`: Filter by kind (page, entity, concept, source, qa)
- `--tags`: Filter by tags (can be repeated)
- `--limit`: Maximum results (default: 10)
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Examples:**
```bash
# Text search
uv run llm-wiki search query "python programming"

# Filter by domain
uv run llm-wiki search query --domain vulpine-solutions

# Filter by tags
uv run llm-wiki search query --tags python --tags api

# Combined search
uv run llm-wiki search query "API design" --domain vulpine-solutions --limit 5
```

**Other search subcommands:**
- `llm-wiki search get PAGE_ID` — Get a specific page by ID
- `llm-wiki search backlinks PAGE_ID` — Show all pages linking to a given page

---

### `llm-wiki ingest file`

Ingest a file into the wiki inbox.

```bash
llm-wiki ingest file FILE_PATH [OPTIONS]
```

**Arguments:**
- `FILE_PATH`: Path to file to ingest

**Options:**
- `--domain`: Target domain (overrides auto-routing)
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
uv run llm-wiki ingest file my-notes.md --domain vulpine-solutions
```

**Note:** The daemon will process the file automatically.

---

### `llm-wiki ingest text`

Create a page from text content.

```bash
llm-wiki ingest text CONTENT [OPTIONS]
```

**Arguments:**
- `CONTENT`: Page content (markdown)

**Options:**
- `--title`: Page title (required)
- `--domain`: Target domain (default: `general`)
- `--tags`: Tags for the page (can be repeated)
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
uv run llm-wiki ingest text "Python is a programming language" \
  --title "Python Programming" \
  --domain vulpine-solutions \
  --tags python --tags programming
```

---

### `llm-wiki ingest obsidian`

Import an Obsidian vault into the wiki.

```bash
llm-wiki ingest obsidian VAULT_PATH [OPTIONS]
```

**Arguments:**
- `VAULT_PATH`: Path to Obsidian vault directory

---

### `llm-wiki ingest failed`

Manage failed ingestions.

**Subcommands:**
- `list` — List failed ingests
- `retry` — Retry a failed ingestion
- `approve` — Mark a failed ingestion as approved despite failure
- `discard` — Discard a failed ingestion

---

### `llm-wiki ingest stats`

Show ingestion statistics including failed files.

---

### `llm-wiki claims extract`

Extract factual claims from a wiki page.

```bash
llm-wiki claims extract PAGE_ID [OPTIONS]
```

**Options:**
- `--wiki-base`: Path to wiki base (default: `wiki_system`)

---

### `llm-wiki claims list`

List all indexed claims for a wiki page.

```bash
llm-wiki claims list PAGE_ID [OPTIONS]
```

---

### `llm-wiki claims search`

Search claims across all wiki pages.

```bash
llm-wiki claims search QUERY [OPTIONS]
```

---

### `llm-wiki changes list`

List recent changes across all pages (or for a specific page).

```bash
llm-wiki changes list [OPTIONS]
```

---

### `llm-wiki changes diff`

Show a diff of all changes to a page in a time window.

```bash
llm-wiki changes diff PAGE_ID --from DATE --to DATE
```

---

### `llm-wiki changes show`

Show full details of a single change entry.

```bash
llm-wiki changes show CHANGE_ID
```

---

### `llm-wiki changes stats`

Show change log statistics.

```bash
llm-wiki changes stats [OPTIONS]
```

---

### `llm-wiki govern check`

Run governance checks and generate report.

```bash
llm-wiki govern check [OPTIONS]
```

**Options:**
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
uv run llm-wiki govern check
```

**Output:**
- Lint issues count
- Stale pages count
- Low quality pages count
- Full report path

---

### `llm-wiki govern contradictions`

Detect and report contradictions across pages.

```bash
llm-wiki govern contradictions [OPTIONS]
```

**Options:**
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)
- `--min-confidence`: Minimum confidence threshold (default: `0.6`)
- `--output`: Custom output file path

---

### `llm-wiki govern duplicates`

Detect and report duplicate entity pages.

```bash
llm-wiki govern duplicates [OPTIONS]
```

---

### `llm-wiki govern merge-duplicate`

Merge a duplicate page into the primary page.

```bash
llm-wiki govern merge-duplicate DUPLICATE_ID PRIMARY_ID [OPTIONS]
```

---

### `llm-wiki govern routing-mistakes`

Detect pages that may be routed to the wrong domain.

```bash
llm-wiki govern routing-mistakes [OPTIONS]
```

---

### `llm-wiki govern rebuild-index`

Rebuild search indexes.

```bash
llm-wiki govern rebuild-index [OPTIONS]
```

**Options:**
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Output:**
- Metadata index pages count
- Fulltext index documents count

---

### `llm-wiki govern update-backlinks`

Update the backlink index for pages that have changed.

```bash
llm-wiki govern update-backlinks [OPTIONS]
```

---

### `llm-wiki govern query-log`

Show query log statistics (repeated queries, top searches, oldest entries).

```bash
llm-wiki govern query-log [OPTIONS]
```

**Options:**
- `--json`: Emit machine-parseable JSON output instead of human-readable text
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
# Human-readable output
uv run llm-wiki govern query-log
```

**Output (human-readable):**
```
Total queries: 142
Oldest entry:  2026-01-15T08:30:00

Top repeated queries:
    5x  how to configure nginx reverse proxy
    3x  setting up ollama with llama3.2
    2x  what is a knowledge graph
```

**Output (--json):**
```json
{
  "total_rows": 142,
  "oldest_entry": "2026-01-15T08:30:00",
  "top_queries": [
    {"query": "how to configure nginx reverse proxy", "hits": 5},
    {"query": "setting up ollama with llama3.2", "hits": 3}
  ]
}
```

The query log (`wiki_system/state/query_log.db`) is automatically pruned during each governance sweep, removing entries older than 90 days (configurable via `synthesis_cache_log_retention_days` in `daemon.yaml`).

---

### `llm-wiki govern clean-broken-links`

Remove stale broken links from the backlink index.

```bash
llm-wiki govern clean-broken-links [OPTIONS]
```

---

### `llm-wiki export all`

Export all formats (llms.txt, graph, sitemap, JSON sidecars).

```bash
llm-wiki export all [OPTIONS]
```

**Options:**
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
uv run llm-wiki export all
```

**Outputs:**
- `wiki_system/exports/llms.txt`
- `wiki_system/exports/graph.json`
- `wiki_system/exports/sitemap.xml`
- JSON sidecars alongside each markdown file

---

### `llm-wiki export llmstxt`

Export to llms.txt format for LLM consumption.

```bash
llm-wiki export llmstxt [OPTIONS]
```

**Options:**
- `--output`: Output file path (default: `wiki_system/exports/llms.txt`)
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

---

### `llm-wiki export llmsfull`

Export to llms-full.txt format with comprehensive page data.

```bash
llm-wiki export llmsfull [OPTIONS]
```

---

### `llm-wiki export graph`

Export graph of page relationships.

```bash
llm-wiki export graph [OPTIONS]
```

---

### `llm-wiki graph edges`

Show edges from/to a node in the graph.

```bash
llm-wiki graph edges NODE_ID [OPTIONS]
```

---

### `llm-wiki graph neighbors`

Find all nodes reachable within N hops.

```bash
llm-wiki graph neighbors NODE_ID [OPTIONS]
```

---

### `llm-wiki graph path`

Find directed paths between two nodes.

```bash
llm-wiki graph path SOURCE TARGET [OPTIONS]
```

---

### `llm-wiki graph stats`

Show graph edge index statistics.

```bash
llm-wiki graph stats [OPTIONS]
```

---

### `llm-wiki graph subgraph`

Extract the subgraph containing the given nodes.

```bash
llm-wiki graph subgraph NODE1 NODE2 [OPTIONS]
```

---

### `llm-wiki promote check`

Check for pages eligible for promotion to shared space.

```bash
llm-wiki promote check [OPTIONS]
```

Shows all pages eligible for promotion with scores and cross-domain references.

---

### `llm-wiki promote process`

Process all promotion candidates.

```bash
llm-wiki promote process [OPTIONS]
```

Auto-promotes eligible pages or adds them to the review queue.

---

### `llm-wiki query relationships`

Query relationships in the wiki.

```bash
llm-wiki query relationships [OPTIONS]
```

---

### `llm-wiki query rebuild-relationships`

Rebuild the relationship index from all wiki pages.

```bash
llm-wiki query rebuild-relationships [OPTIONS]
```

---

### `llm-wiki review add`

Manually add an item to the review queue.

```bash
llm-wiki review add [OPTIONS]
```

---

### `llm-wiki review list`

List review queue items.

```bash
llm-wiki review list [OPTIONS]
```

---

### `llm-wiki review show`

Show details of a review item.

```bash
llm-wiki review show ITEM_ID
```

---

### `llm-wiki review approve`

Approve a review item.

```bash
llm-wiki review approve ITEM_ID [OPTIONS]
```

---

### `llm-wiki review reject`

Reject a review item.

```bash
llm-wiki review reject ITEM_ID [OPTIONS]
```

---

### `llm-wiki review defer`

Defer a review item for later.

```bash
llm-wiki review defer ITEM_ID [OPTIONS]
```

---

### `llm-wiki review stats`

Show review queue statistics.

```bash
llm-wiki review stats [OPTIONS]
```

---

### `llm-wiki review cleanup`

Clean up old resolved review items.

```bash
llm-wiki review cleanup [OPTIONS]
```

---

### `llm-wiki integrate apply`

Apply integration to a page.

```bash
llm-wiki integrate apply PAGE_ID [OPTIONS]
```

---

### `llm-wiki integrate check`

Preview integration result without applying changes.

```bash
llm-wiki integrate check PAGE_ID [OPTIONS]
```

---

### `llm-wiki integrate history`

Show integration history for a page.

```bash
llm-wiki integrate history PAGE_ID
```

---

### `llm-wiki integrate rollback`

Rollback integration to previous state.

```bash
llm-wiki integrate rollback PAGE_ID [OPTIONS]
```

---

### `llm-wiki integrate strategies`

Show merge strategy configuration.

```bash
llm-wiki integrate strategies
```

---

### `llm-wiki trigger JOB_NAME`

Run a daemon job manually from the command line.

```bash
llm-wiki trigger JOB_NAME [OPTIONS]
```

**Available jobs:**
- `inbox-scan` — Scan inbox for new files
- `queue-to-pages` — Migrate queued files to published pages
- `governance` — Run governance checks on published pages
- `export` — Re-run all export formats
- `index-rebuild` — Rebuild all search indexes
- `retry-failed-ingests` — Retry previously failed ingestions
- `review-queue` — Populate the review queue
- `promotion` — Run page promotion checks

---

### `llm-wiki hooks install`

Install Claude Code session capture hooks (`SessionEnd` and `PreCompact`)
so that every Claude Code session lands as a transcript in
`wiki_system/inbox/new/`.

```bash
llm-wiki hooks install [OPTIONS]
```

**Options:**
- `--scope {user,project}`: Write to `~/.claude/settings.json` or
  `.claude/settings.json` (default: `project`)
- `--wiki-base PATH`: Wiki base used as the inbox target (default:
  `wiki_system`)
- `--dry-run`: Print merged settings instead of writing

**Behavior:**
- Merges with existing hook entries — never overwrites unrelated hooks.
- Idempotent: running twice does not duplicate the llm-wiki entry.
- Command uses the current Python interpreter (`sys.executable`) so a
  venv/uv install points at the right Python, not bare `python` on PATH.
- Script is resolved from the packaged resource
  `llm_wiki/hook_templates/capture_session.py`, so it works in both
  editable and wheel installs.

**Example:**
```bash
# Preview without writing
uv run llm-wiki hooks install --dry-run

# Install at project scope
uv run llm-wiki hooks install

# Install at user scope (applies to every project that uses Claude Code)
uv run llm-wiki hooks install --scope user
```

---

### `llm-wiki hooks uninstall`

Remove llm-wiki session capture hooks from Claude Code settings.

```bash
llm-wiki hooks uninstall [OPTIONS]
```

**Options:**
- `--scope {user,project}`: Which settings file to clean (default: `project`)

**Behavior:**
- Only removes entries whose command references `capture_session.py`.
- Leaves any other hook entries intact.
- If the event list becomes empty, the event key is dropped entirely.

---

## Common Workflows

### Initial Setup
```bash
# 1. Initialize wiki
uv run llm-wiki init

# 2. Configure domains in config/domains.yaml

# 3. Start daemon (optional for automated processing)
uv run llm-wiki daemon
```

### Adding Content
```bash
# Drop file in inbox (daemon will process)
cp my-notes.md wiki_system/inbox/

# Or use CLI directly
uv run llm-wiki ingest file my-notes.md --domain vulpine-solutions
```

### Searching
```bash
# Search all content
uv run llm-wiki search query "python"

# Search specific domain
uv run llm-wiki search query "API" --domain vulpine-solutions

# Get specific page
uv run llm-wiki search get python-programming
```

### Governance
```bash
# Full governance check
uv run llm-wiki govern check

# Rebuild indexes
uv run llm-wiki govern rebuild-index

# Check for contradictions
uv run llm-wiki govern contradictions

# Export for LLM context
uv run llm-wiki export all
```

### Review Queue
```bash
# View pending items
uv run llm-wiki review list

# Approve an item
uv run llm-wiki review approve item-id

# Check for promotion candidates
uv run llm-wiki promote check
```

### Integration
```bash
# Preview integration
uv run llm-wiki integrate check page-id

# Apply integration
uv run llm-wiki integrate apply page-id
```

---

## Exit Codes

- `0`: Success
- `1`: Error (check error message for details)

---

## Environment Variables

None required for basic operation.

For LLM extraction:
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key

---

## See Also

- [SETUP.md](SETUP.md) - Installation and configuration
- [AGENT_CONVENTIONS.md](AGENT_CONVENTIONS.md) - Usage conventions
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
