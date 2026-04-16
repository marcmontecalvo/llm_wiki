# Agent Support Matrix

Integration status for different AI agents and tools.

## Overview

This document tracks which features are implemented for each agent/tool integration.

**Legend:**
- ✅ Implemented and tested
- 🔄 Partially implemented
- ❌ Not implemented
- 📋 Planned (see issues)

---

## Claude Code

**Status:** ✅ **Primary Integration**

**Official Support:** Yes (this is the reference implementation)

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| Skills | ✅ | `/wiki`, `/ingest`, `/export`, `/govern` |
| Bootstrap | ✅ | `.claude/bootstrap.md` |
| Project Context | ✅ | `.claude/` directory structure |
| Slash Commands | ✅ | Full skill integration |
| Conventions | ✅ | `docs/AGENT_CONVENTIONS.md` |

### Available Skills

**`.claude/skills/wiki.md`** - Search wiki
```bash
/wiki python programming
/wiki --domain vulpine-solutions api
```

**`.claude/skills/ingest.md`** - Add content
```bash
/ingest my-notes.md --domain homelab
```

**`.claude/skills/export.md`** - Generate exports
```bash
/export
```

**`.claude/skills/govern.md`** - Run governance checks
```bash
/govern
```

### Setup

1. Open project in Claude Code
2. Skills automatically loaded from `.claude/skills/`
3. Bootstrap context loaded from `.claude/bootstrap.md`
4. Use slash commands directly

### Example Workflow

```
User: /wiki kubernetes
Claude: [Searches wiki and returns results]

User: /ingest my-k8s-notes.md --domain homelab
Claude: [Ingests file into homelab domain]

User: /govern
Claude: [Runs governance checks and shows report]
```

---

## GitHub Copilot

**Status:** ✅ **Implemented** (Issue #77)

**Official Support:** Yes

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| Workspace Context | ✅ | `.github/copilot-instructions.md` |
| Custom Instructions | ✅ | Full wiki integration |
| Chat Integration | ✅ | Via Python API |
| Code Completion | ✅ | Wiki-aware suggestions |

### Implementation

Created `.github/copilot-instructions.md` with:
- System overview and structure
- Domain documentation
- Quick reference for querying, adding content
- Page format and frontmatter schema
- CLI commands and development guide
- Links to full documentation

---

## Cursor IDE

**Status:** ✅ **Implemented** (Issue #76)

**Official Support:** Yes (implemented)

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| `.cursor/rules` | ✅ | Multi-file rule system |
| Context Files | ✅ | `.cursor/rules/00-llm-wiki.mdc` |
| Custom Commands | ✅ | @wiki, @ingest, @export, @govern |
| Composer Integration | ✅ | Full command support |
| Search Rules | ✅ | `.cursor/rules/01-search.mdc` |
| Ingest Rules | ✅ | `.cursor/rules/02-ingest.mdc` |
| Govern Rules | ✅ | `.cursor/rules/03-govern.mdc` |
| Export Rules | ✅ | `.cursor/rules/04-export.mdc` |
| Index | ✅ | `.cursor/rules/index.mdc` |

### Available Commands

**@wiki** - Search wiki
```
@wiki python
@wiki kubernetes --domain homelab
@wiki api --tags rest,http
```

**@ingest** - Add content
```
@ingest my-notes.md --domain personal
@ingest --text "content" --domain vulpine-solutions
```

**@export** - Generate exports
```
@export all
@export llms.txt
@export graph
```

**@govern** - Run governance
```
@govern check
@govern rebuild-index
@govern report
```

### Setup

1. Open project in Cursor IDE
2. Rules automatically loaded from `.cursor/rules/`
3. Use @-commands in AI chat

---

## Obsidian

**Status:** ✅ **Implemented** (Issue #78)

**Official Support:** Yes

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| Vault Import | ✅ | Via `llm-wiki ingest obsidian` command |
| Markdown Compatibility | ✅ | Standard markdown |
| Wikilinks | ✅ | `[[page-id]]` supported |
| Embedded Files | ✅ | `![[page-id]]` supported |
| Hashtags | ✅ | Auto-extracted to tags |
| Frontmatter | ✅ | Compatible format |
| Graph View | 🔄 | Export compatible |

### Usage

**Import a vault:**
```bash
# Import full Obsidian vault to personal domain
uv run llm-wiki ingest obsidian ~/Documents/Obsidian/MyVault --domain personal

# Import to specific domain
uv run llm-wiki ingest obsidian ~/Documents/Obsidian/WorkNotes --domain work
```

**What gets imported:**
- All markdown files from the vault (excluding `.obsidian` and `templates` folders)
- Wikilinks `[[page-id]]` → preserved
- Embedded files `![[page-id]]` → converted to wikilinks
- Hashtags `#tag` → extracted to tags metadata
- Frontmatter → parsed and included in metadata
- Filename → used as page ID

**The daemon processes imported files automatically.**

---

## OpenAI Codex / ChatGPT

**Status:** 🔄 **Partial Support**

**Official Support:** No dedicated integration

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| API Access | ✅ | Via Python API |
| Export Loading | ✅ | Can load llms.txt |
| Direct Integration | ❌ | No dedicated plugin |
| Custom GPTs | ❌ | Not implemented |

### Current Usage

**Load Wiki Context:**
```python
# Read llms.txt export
wiki_context = open("wiki_system/exports/llms.txt").read()

# Use in OpenAI API call
import openai

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": f"Wiki context:\n{wiki_context}"},
        {"role": "user", "content": "Question about wiki content..."}
    ]
)
```

**Query Wiki:**
```python
from llm_wiki.query.search import WikiQuery
from pathlib import Path

wiki = WikiQuery(wiki_base=Path("wiki_system"))
results = wiki.search("kubernetes")

# Format for OpenAI
context = "\n\n".join([
    f"# {r['title']}\n{r.get('summary', '')}"
    for r in results
])
```

---

## Python API

**Status:** ✅ **Full Support**

**Official Support:** Yes (primary interface)

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| Search | ✅ | `WikiQuery` class |
| Ingest | ✅ | Adapter system |
| Export | ✅ | All exporters available |
| Governance | ✅ | Job classes |
| Configuration | ✅ | Pydantic models |

### API Example

```python
from pathlib import Path
from llm_wiki.query.search import WikiQuery
from llm_wiki.export.llmstxt import LLMSTxtExporter
from llm_wiki.daemon.jobs.governance import GovernanceJob

wiki_base = Path("wiki_system")

# Search
wiki = WikiQuery(wiki_base=wiki_base)
results = wiki.search("python", domain="vulpine-solutions", limit=10)

# Export
exporter = LLMSTxtExporter(wiki_base=wiki_base)
output_path = exporter.export_all()

# Governance
gov = GovernanceJob(wiki_base=wiki_base)
stats = gov.execute()
```

### Documentation

See:
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design
- [CLI.md](CLI.md) - Command examples
- Source code: `src/llm_wiki/`

---

## MCP (Model Context Protocol)

**Status:** 🔄 **Future Consideration**

**Official Support:** Not yet

### Features

| Feature | Status | Notes |
|---------|--------|-------|
| MCP Server | ❌ | Not implemented |
| Resource Endpoints | ❌ | Planned |
| Tool Definitions | ❌ | Planned |

### Potential Integration

The wiki system could expose MCP endpoints:

**Resources:**
- `wiki://page/{id}` - Get page content
- `wiki://search?q={query}` - Search wiki
- `wiki://domain/{domain}` - List domain pages

**Tools:**
- `wiki.search(query, domain, tags)` - Search tool
- `wiki.get_page(id)` - Retrieve page
- `wiki.ingest(content, metadata)` - Add content

**Note:** MCP integration not currently planned. Open an issue if interested.

---

## Integration Roadmap

### Phase 1: Claude Code (✅ Complete)
- Basic skills
- Bootstrap documentation
- Convention guide

### Phase 2: IDE Integration (📋 Planned)
- Cursor IDE support (#76)
- GitHub Copilot support (#77) ✅ Complete
- Obsidian vault adapter (#78)

### Phase 3: Advanced Features (Future)
- Custom GPTs
- MCP protocol
- VS Code extension
- Browser extension

---

## Adding New Agent Support

To add support for a new agent/tool:

1. **Create Bootstrap Doc**
   - Copy `.claude/bootstrap.md` as template
   - Adapt to agent's format
   - Add agent-specific features

2. **Define Commands/Skills**
   - Map wiki operations to agent commands
   - Create command definitions
   - Add examples

3. **Add Configuration**
   - Agent-specific config files
   - Environment setup
   - Path configuration

4. **Test Integration**
   - Verify all features work
   - Document known limitations
   - Add to this matrix

5. **Update Documentation**
   - Add section to this file
   - Update README.md
   - Create agent-specific guide

---

## Feature Comparison

| Feature | Claude Code | Cursor | Copilot | Obsidian | Python API | OpenAI |
|---------|------------|--------|---------|----------|------------|--------|
| Search | ✅ | ✅ | 📋 | 📋 | ✅ | 🔄 |
| Ingest | ✅ | ✅ | 📋 | ✅ | ✅ | ❌ |
| Export | ✅ | ✅ | 📋 | ❌ | ✅ | ❌ |
| Govern | ✅ | ✅ | 📋 | ❌ | ✅ | ❌ |
| Bootstrap | ✅ | ✅ | 📋 | 📋 | ✅ | ❌ |
| Skills/Commands | ✅ | ✅ | 📋 | ❌ | N/A | ❌ |
| Context Loading | ✅ | ✅ | 📋 | ❌ | ✅ | 🔄 |

---

## Community Contributions

Want to add support for your favorite agent? See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

**Priority integrations:**
1. Cursor IDE
2. GitHub Copilot
3. Obsidian vault import
4. VS Code extension

---

## See Also

- [AGENT_CONVENTIONS.md](AGENT_CONVENTIONS.md) - Cross-agent conventions
- [CLI.md](CLI.md) - Command-line interface
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- `.claude/bootstrap.md` - Claude Code bootstrap guide
