# Cursor IDE Setup for LLM Wiki

This guide covers how to use Cursor IDE with the LLM wiki system.

## Installation

1. Download Cursor IDE from [cursor.sh](https://cursor.sh)
2. Install the application
3. Open this project in Cursor: `File > Open Folder > select llm_wiki`

## Workspace Setup

Cursor automatically loads project rules from `.cursor/rules/`. No additional configuration needed.

**Note:** The wiki uses the modern `.mdc` (Markdown Cursor) format for rules, stored in `.cursor/rules/` directory, rather than a single `.cursorrules` file. This allows for modular, organized rule sets that can be individually enabled/disabled.

### Initial Setup

```bash
# Install dependencies
uv sync

# Initialize wiki (if not already done)
uv run llm-wiki init

# Verify installation
uv run llm-wiki search query "test"
```

## Common Workflows

### Searching the Wiki

In Cursor's AI chat (Cmd+L / Ctrl+L), type:
```
@wiki python
@wiki kubernetes --domain homelab
@wiki api --tags rest,http
```

### Adding Content

```
@ingest my-notes.md --domain personal
@ingest --text "My content here" --domain vulpine-solutions --title "My Page"
```

Or drop files in `wiki_system/inbox/` for automatic processing.

### Running Governance

```
@govern check
@govern rebuild-index
@govern report
```

### Exporting Data

```
@export all
@export llms.txt
@export graph
```

## Keyboard Shortcuts

| Action | macOS | Windows/Linux |
|--------|-------|---------------|
| AI Chat | Cmd+L | Ctrl+L |
| Command Palette | Cmd+Shift+P | Ctrl+Shift+P |
| Quick File | Cmd+P | Ctrl+P |
| Terminal | Cmd+` | Ctrl+` |
| Save | Cmd+S | Ctrl+S |
| Find | Cmd+F | Ctrl+F |

## Development Commands

```bash
# Run tests
uv run pytest

# Run specific test file
uv run pytest tests/test_query.py

# Lint code
uv run ruff check .

# Format code
uv run ruff format .

# Type check
uv run mypy src/

# Run CLI
uv run llm-wiki --help
```

## Tips and Tricks

### 1. Use Domain Filters

Always specify domain when you know it:
```
@wiki k3s --domain homelab
```
This returns more relevant results.

### 2. Use Tag Filters

Combine domain and tags for precision:
```
@wiki monitoring --domain homelab --tags prometheus,grafana
```

### 3. Check Recent Changes

Before editing, check the latest governance report:
```
@govern report
```

### 4. Use the Inbox

For bulk ingestion, drop multiple files in `wiki_system/inbox/`:
- Markdown files (`.md`)
- Text files (`.txt`)
- Frontmatter is auto-detected

### 5. Link Pages Correctly

Use wiki-style links: `[[page-id]]`
- IDs are kebab-case: `python-programming`
- Links work across domains

## Integration with Cursor Rules

The wiki system provides these @-commands:

| Command | Description |
|---------|-------------|
| @wiki | Search wiki pages |
| @ingest | Add content to wiki |
| @export | Generate exports |
| @govern | Run quality checks |
| @get | Get specific page |

## Cursor IDE Integration Features

The wiki provides several Cursor-specific capabilities:

### Auto-Complete with Wiki Context
- Wiki page IDs are indexed for auto-completion when typing `[[`
- Type `[[python` to see matching wiki pages
- Domain prefixes help filter: `homelab/k3s` shows homelab domain k3s pages

### Inline Suggestions
- AI chat suggests wiki-related commands as you type
- Context-aware suggestions based on current file
- Quick-insert for wiki links: type page ID, press Tab to complete

### Command Palette Integration
- Access wiki commands via `Cmd+Shift+P` / `Ctrl+Shift+P`
- Search for "wiki" to see all wiki-related commands:
  - `Wiki: Search` - Open search dialog
  - `Wiki: Ingest` - Add new content
  - `Wiki: Export` - Generate exports
  - `Wiki: Governance` - Run quality checks

### File Navigation Shortcuts
- Quick file open (`Cmd+P` / `Ctrl+P`) includes wiki pages
- Wiki domains appear as folder groups
- Recent wiki pages appear in "Recent Files" section

### AI Chat Integration
The @-commands work in Cursor's AI chat (Cmd+L / Ctrl+L):

```
@wiki kubernetes --domain homelab --tags k8s,container
@ingest notes.md --domain personal
@export llms.txt
@govern check --domain vulpine-solutions
```

### Composer Features
When using Cursor Composer (Cmd+Enter / Ctrl+Enter):
- Multi-file wiki edits supported
- Batch content updates across domains
- Generate wiki pages from code documentation

## Troubleshooting

### Rules Not Loading

Check that `.cursor/rules/` exists and contains `.mdc` files.

### Import Errors

Run `uv sync` to ensure dependencies are installed.

### Search Returns No Results

Rebuild the index:
```
@govern rebuild-index
```

### Permission Errors

Ensure wiki directories are writable:
```bash
chmod -R 755 wiki_system/
```

## Related Documentation

- [AGENT_CONVENTIONS.md](../AGENT_CONVENTIONS.md) - Wiki conventions
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md) - Feature status
- [.claude/bootstrap.md](../.claude/bootstrap.md) - Claude Code reference