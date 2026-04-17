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

Start the wiki daemon for continuous processing.

```bash
llm-wiki daemon [--config-dir PATH]
```

**Options:**
- `--config-dir`: Path to configuration directory (default: `config`)

**Example:**
```bash
uv run llm-wiki daemon
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
- `--kind`: Filter by kind (page, entity, concept)
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

---

### `llm-wiki search get`

Get a specific page by ID.

```bash
llm-wiki search get PAGE_ID [OPTIONS]
```

**Arguments:**
- `PAGE_ID`: Page identifier (kebab-case)

**Options:**
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
uv run llm-wiki search get python-programming
```

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

### `llm-wiki govern rebuild-index`

Rebuild search indexes.

```bash
llm-wiki govern rebuild-index [OPTIONS]
```

**Options:**
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
uv run llm-wiki govern rebuild-index
```

**Output:**
- Metadata index pages count
- Fulltext index documents count

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

**Example:**
```bash
uv run llm-wiki export llmstxt --output custom-output.txt
```

---

### `llm-wiki export graph`

Export graph of page relationships.

```bash
llm-wiki export graph [OPTIONS]
```

**Options:**
- `--output`: Output file path (default: `wiki_system/exports/graph.json`)
- `--wiki-base`: Path to wiki base directory (default: `wiki_system`)

**Example:**
```bash
uv run llm-wiki export graph --output my-graph.json
```

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

### Maintenance
```bash
# Check quality
uv run llm-wiki govern check

# Rebuild indexes if needed
uv run llm-wiki govern rebuild-index

# Export for LLM context
uv run llm-wiki export all
```

---

## Exit Codes

- `0`: Success
- `1`: Error (check error message for details)

---

## Environment Variables

None required for basic operation.

For LLM extraction (future):
- `OPENAI_API_KEY`: OpenAI API key
- `ANTHROPIC_API_KEY`: Anthropic API key

---

## See Also

- [SETUP.md](SETUP.md) - Installation and configuration
- [AGENT_CONVENTIONS.md](AGENT_CONVENTIONS.md) - Usage conventions
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
