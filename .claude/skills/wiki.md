# Wiki Query Skill

Search and query the wiki system.

## Usage

```
/wiki [query] [--domain DOMAIN] [--kind KIND] [--tags TAG1,TAG2]
```

## Description

Search wiki pages using fulltext and metadata filters.

## Implementation

```python
from pathlib import Path
from llm_wiki.query.search import WikiQuery

# Initialize query interface
wiki = WikiQuery(wiki_base=Path("wiki_system"))

# Parse arguments
query = args.get("query")
domain = args.get("domain")
kind = args.get("kind")
tags = args.get("tags", "").split(",") if args.get("tags") else None

# Search
results = wiki.search(
    query=query,
    domain=domain,
    kind=kind,
    tags=tags,
    limit=10
)

# Display results
if results:
    print(f"Found {len(results)} pages:")
    for r in results:
        tags_str = ", ".join(r["tags"]) if r["tags"] else "no tags"
        print(f"\n**{r['title']}** ({r['domain']})")
        print(f"  ID: {r['page_id']}")
        print(f"  Kind: {r['kind']}")
        print(f"  Tags: {tags_str}")
        print(f"  Score: {r['score']:.3f}")
else:
    print("No results found.")
```

## Examples

- `/wiki python` - Search for "python"
- `/wiki --domain tech --kind entity` - List tech entities
- `/wiki api --tags rest,http` - Search with tag filter
