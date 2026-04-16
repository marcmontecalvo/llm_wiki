# Add Page Prompt

Use this template to add new content to the wiki.

## From File

```
Ingest the file: [path-to-file]
Domain: [target-domain]

Example:
Ingest the file: /Users/me/notes/python-tips.md
Domain: personal
```

## From Text

```
Create a new page with the following content:

Title: [page-title]
Domain: [domain-name]
Kind: [page|entity|concept|source] (optional)
Tags: [tag1, tag2] (optional)

Content:
[your content here]

Example:
Title: Docker Compose Best Practices
Domain: homelab
Kind: concept
Tags: docker, compose, devops

Content:
Docker Compose is a tool for defining multi-container applications...

```

## Frontmatter Template

When creating pages manually, use this frontmatter format:

```yaml
---
title: Your Page Title
domain: domain-name
kind: page
tags:
  - tag1
  - tag2
summary: Brief description of the page content
---
```

## Domain Selection Guide

| Domain | Use For |
|--------|---------|
| vulpine-solutions | Business, operations, client work |
| home-assistant | Home automation, IoT |
| homelab | Infrastructure, self-hosted services |
| personal | Personal notes, plans, hobbies |
| general | Uncategorized content |

## Content Types

### page
Standard wiki article or documentation.

### entity
People, organizations, technologies, tools, products.

### concept
Ideas, methodologies, patterns, processes.

### source
Reference documents, external links, source materials.

## Tips

1. **Use descriptive titles** - Clear, specific titles help with search
2. **Add relevant tags** - Improves discoverability
3. **Include summaries** - Brief descriptions help in search results
4. **Link related pages** - Use `[[page-id]]` to link to other wiki pages
5. **Drop in inbox** - Alternatively, drop files in `wiki_system/inbox/` for auto-processing