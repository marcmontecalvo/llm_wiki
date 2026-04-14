# Wiki Export Skill

Generate wiki exports.

## Usage

```
/export [--format FORMAT] [--domain DOMAIN]
```

## Description

Export wiki content in various formats (llms.txt, json, graph, sitemap).

## Implementation

```python
from pathlib import Path
from llm_wiki.daemon.jobs.export import ExportJob

wiki_base = Path("wiki_system")
format_type = args.get("format", "all")
domain = args.get("domain")

print(f"Exporting wiki (format: {format_type})...")

try:
    if format_type == "all":
        # Run full export job
        job = ExportJob(wiki_base=wiki_base)
        result = job.execute()

        if result["status"] == "success":
            print("\n✓ Export complete:")
            print(f"  - llms.txt: {result['llmstxt_path']}")
            print(f"  - JSON sidecars: {result['json_sidecars']} files")
            print(f"  - Graph: {result['graph_path']}")
            print(f"  - Sitemap: {result['sitemap_path']}")
        else:
            print(f"\n✗ Export failed: {result.get('error')}")

    elif format_type == "llms":
        from llm_wiki.export.llmstxt import LLMSTxtExporter
        exporter = LLMSTxtExporter(wiki_base=wiki_base)

        if domain:
            path = exporter.export_domain(domain)
        else:
            path = exporter.export_all()

        print(f"\n✓ Exported llms.txt: {path}")

    elif format_type == "graph":
        from llm_wiki.export.graph import GraphExporter
        exporter = GraphExporter(wiki_base=wiki_base)
        path = exporter.export_json()
        print(f"\n✓ Exported graph: {path}")

    else:
        print(f"Unknown format: {format_type}")
        print("Valid formats: all, llms, graph")

except Exception as e:
    print(f"\n✗ Export error: {e}")
```

## Examples

- `/export` - Export all formats
- `/export --format llms` - Export llms.txt only
- `/export --format llms --domain tech` - Export tech domain to llms.txt
