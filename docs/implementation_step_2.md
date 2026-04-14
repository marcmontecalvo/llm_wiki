# Implementation Step 2 - Ingest, routing, and normalization

## Objective

Get documents into the system cleanly and predictably.

## Inputs to support first

Start with only these:
- markdown files
- plain text files
- agent session transcripts
  - Claude Code
  - Codex CLI
  - Cursor
- manual notes dropped into inbox

Do not start with PDFs, web crawlers, RSS, or CVE feeds.

## Build now

### 1. Inbox watcher
Watch `wiki_system/inbox/` for new files.

### 2. Source adapters
Build adapters with a common interface:
- `can_parse()`
- `extract_metadata()`
- `normalize_to_markdown()`

### 3. Domain router
Implement routing in this order:
1. explicit override from file metadata
2. folder/source mapping rules
3. lexical/domain classifier
4. fallback to `general`

Every routing decision should emit:
- chosen domain
- confidence
- reason
- fallback flag

### 4. Normalization
All inputs become normalized markdown with standard frontmatter.

Required frontmatter:
- `id`
- `title`
- `source_type`
- `source_path`
- `created_at`
- `ingested_at`
- `domain`
- `tags`
- `status`

## Borrow directly from

### Pratiyush/llm-wiki
Adapter and transcript-ingest mindset:
https://github.com/Pratiyush/llm-wiki

Relevant docs worth reading:
- https://github.com/Pratiyush/llm-wiki/blob/master/docs/getting-started.md
- https://github.com/Pratiyush/llm-wiki/blob/master/docs/adapters/cursor.md
- https://github.com/Pratiyush/llm-wiki/blob/master/docs/adapters/obsidian.md

### Ar9av/obsidian-wiki
Cross-agent wiring/bootstrap ideas:
https://github.com/Ar9av/obsidian-wiki

## Deliverable

By the end of Step 2, dropping a transcript or markdown note into the inbox should deterministically produce a normalized file in the correct domain queue.
