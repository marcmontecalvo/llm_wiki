# GitHub Copilot Setup Guide

How to enable and use GitHub Copilot with the LLM Wiki system.

## Enabling Copilot

### For Individual Use

1. **Install the GitHub Copilot extension:**
   - VS Code: Install "GitHub Copilot" extension from Marketplace
   - JetBrains: Install "GitHub Copilot" plugin from JetBrains Marketplace

2. **Sign in to GitHub:**
   - Click the Copilot icon in your IDE toolbar
   - Authenticate with your GitHub account
   - Ensure you have an active Copilot subscription

3. **Project-specific setup:**
   - The wiki automatically loads `.github/copilot-instructions.md`
   - No additional configuration needed

### For Organization

1. **Admin setup:**
   - Enable Copilot in organization settings
   - Configure seat assignments for team members

2. **Policy configuration:**
   - Set up allowed repository access
   - Configure code suggestions permissions

## Best Practices for Prompting

### Effective Prompts

**Good prompt:**
```
Add a new domain called "ai-projects" to the wiki. Show the config/domains.yaml changes needed and create a minimal page structure.
```

**Better prompt with context:**
```
I need to add a new domain "ai-projects" for tracking machine learning projects in the wiki. 
Following the patterns in docs/AGENT_CONVENTIONS.md:
1. What changes are needed in config/domains.yaml?
2. Create the domain directory structure
3. Add an initial "readme" page with frontmatter
```

**Best prompt with explicit requirements:**
```
Add a new domain "ai-projects" for ML project documentation.

Requirements:
- Use the patterns from .github/copilot-instructions.md
- Domain should appear in config/domains.yaml with description
- Create wiki_system/domains/ai-projects/ directory
- Add an initial page following the format in .github/copilot-instructions.md

Use the existing domains (homelab, vulpine-solutions) as reference for structure.
```

### Asking About Code

**Instead of:**
```
How does ingestion work?
```

**Ask:**
```
How does the InboxWatcher process files in wiki_system/inbox/new/?
Show me the flow from file arrival to domain routing, referencing the key classes.
```

### Asking for Help with Errors

**Include full context:**
```
I'm getting this error when running `uv run llm-wiki ingest file test.md --domain general`:

[error message]

The file has valid frontmatter (id, title, domain). 
What could cause this and how do I fix it?
```

## Example Interactions

### Adding a New Page

```
User: I want to add documentation for a new Python library to the wiki
Copilot: Which domain should this go in - vulpine-solutions or homelab?
User: It's for our MSP business, so vulpine-solutions
Copilot: Here's a template for adding it...

```yaml
---
id: library-name
title: Library Name
domain: vulpine-solutions
kind: entity
tags:
  - python
  - library
summary: Brief description of what this library does.
---
```

### Searching the Wiki

```
User: Find all pages about Proxmox in the homelab domain
Copilot: Here's how to search from code:

from llm_wiki.query.search import WikiQuery
wiki = WikiQuery(wiki_base=Path("wiki_system"))
results = wiki.search("Proxmox", domain="homelab")

Or from CLI:
uv run llm-wiki search query "Proxmox" --domain homelab
```

### Running Governance

```
User: How do I check for stale pages?
Copilot: Use the governance job:

uv run llm-wiki govern check

This runs:
- Metadata validation (required fields, format)
- Staleness detection (pages not updated in 90 days)
- Quality scoring (length, structure, links)
- Orphan detection (unlinked pages)

Results are in wiki_system/reports/governance/
```

## Common Patterns

### Working with Extractors

When Copilot suggests adding extraction logic, ensure you:
1. Follow the BaseExtractor pattern
2. Include proper docstrings (Args, Returns, Example)
3. Add tests in tests/
4. Register in the extraction pipeline

### CLI Development

For new commands, Copilot will suggest Click decorators. Verify:
- Proper argument handling
- Error cases handled
- Help text included

### Testing

Copilot may suggest tests. Ensure:
- Use fixtures from tests/conftest.py
- Mock external dependencies (LLM calls)
- Aim for >90% coverage

## Troubleshooting

### Copilot Not Suggesting Code

1. **Check file is in workspace:**
   - Copilot only works on files in the project

2. **Type more comments:**
   - Copilot learns from context and comments
   - Describe what you want in comments

3. **Check language mode:**
   - Some languages have limited Copilot support

### Poor Suggestions

1. **Provide more context:**
   - Reference the copilot-instructions.md in comments
   - Add example code snippets

2. **Use the right scope:**
   - Single file suggestions work best
   - For multi-file, use natural language first

### Suggestions Out of Date

1. **Check Copilot version:**
   - Update the extension/plugin

2. **Clear caches:**
   - VS Code: Ctrl+Shift+P > "Clear Copilot Caches"

## Related Documentation

- [AGENT_CONVENTIONS.md](AGENT_CONVENTIONS.md) - Cross-agent conventions
- [AGENT_SUPPORT_MATRIX.md](AGENT_SUPPORT_MATRIX.md) - Integration status
- [.github/copilot-instructions.md](../.github/copilot-instructions.md) - Full instructions
- [.github/copilot-snippets.json](../.github/copilot-snippets.json) - Snippet library