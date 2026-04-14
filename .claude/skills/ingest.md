# Wiki Ingest Skill

Add content to the wiki.

## Usage

```
/ingest <file_path> [--domain DOMAIN]
```

## Description

Ingest a file into the wiki system. File is normalized and routed to appropriate domain queue.

## Implementation

```python
from pathlib import Path
import shutil

# Get file path
file_path = Path(args.get("file_path"))
domain = args.get("domain")

if not file_path.exists():
    print(f"Error: File not found: {file_path}")
    return

# Copy to inbox
inbox_dir = Path("wiki_system/inbox")
inbox_dir.mkdir(parents=True, exist_ok=True)

dest = inbox_dir / file_path.name
shutil.copy(file_path, dest)

print(f"✓ Copied {file_path.name} to inbox")

# If domain specified, add metadata
if domain:
    content = dest.read_text()
    if not content.startswith("---"):
        # Add frontmatter with domain
        new_content = f"""---
domain: {domain}
---

{content}"""
        dest.write_text(new_content)
        print(f"✓ Set domain to: {domain}")

print("\nFile will be processed by daemon watcher.")
print("Check wiki_system/domains/{domain}/queue/ for normalized output.")
```

## Examples

- `/ingest notes.md` - Ingest with auto-routing
- `/ingest doc.txt --domain tech` - Ingest to tech domain
