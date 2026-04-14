"""
Export Workflow

This example demonstrates how to export wiki content in various formats
for different use cases.
"""

import json
from pathlib import Path

from llm_wiki.daemon.jobs.export import ExportJob
from llm_wiki.export.graph import GraphExporter
from llm_wiki.export.json_sidecar import JSONSidecarExporter
from llm_wiki.export.llmstxt import LLMSTxtExporter
from llm_wiki.export.sitemap import SitemapExporter

# Setup
wiki_base = Path("wiki_system")
exports_dir = wiki_base / "exports"
exports_dir.mkdir(parents=True, exist_ok=True)

# Example 1: Export to llms.txt for LLM consumption
print("=== LLMs.txt Export ===")
llmstxt_exporter = LLMSTxtExporter(wiki_base=wiki_base)

# Export all domains
llmstxt_path = llmstxt_exporter.export_all(output_file=exports_dir / "llms.txt")
print(f"Exported to: {llmstxt_path}")

# Show preview
if llmstxt_path.exists():
    content = llmstxt_path.read_text()
    lines = content.split("\n")[:50]
    print("\nPreview (first 50 lines):")
    print("-" * 60)
    print("\n".join(lines))
    print("-" * 60)

# Export specific domain
tech_llmstxt = llmstxt_exporter.export_domain(domain="tech", output_file=exports_dir / "tech.txt")
print(f"\nTech domain exported to: {tech_llmstxt}")

# Example 2: Generate JSON sidecars for programmatic access
print("\n\n=== JSON Sidecar Export ===")
json_exporter = JSONSidecarExporter(wiki_base=wiki_base)

stats = json_exporter.export_all()
print(f"Generated JSON sidecars for {stats['files_exported']} pages")
print(f"Total domains: {stats['domains_processed']}")

# Show example sidecar
tech_pages = (wiki_base / "domains" / "tech" / "pages").glob("*.json")
example_json = next(tech_pages, None)

if example_json:
    print(f"\nExample sidecar: {example_json.name}")
    print("-" * 60)
    data = json.loads(example_json.read_text())
    print(json.dumps(data, indent=2)[:500])  # First 500 chars
    print("...")
    print("-" * 60)

# Example 3: Export graph for visualization
print("\n\n=== Graph Export ===")
graph_exporter = GraphExporter(wiki_base=wiki_base)

graph_path = graph_exporter.export(output_file=exports_dir / "graph.json")
print(f"Graph exported to: {graph_path}")

# Load and show stats
if graph_path.exists():
    graph_data = json.loads(graph_path.read_text())
    print("\nGraph statistics:")
    print(f"  Nodes (pages): {len(graph_data['nodes'])}")
    print(f"  Edges (links): {len(graph_data['edges'])}")

    # Show node types
    node_types: dict[str, int] = {}
    for node in graph_data["nodes"]:
        kind = node.get("kind", "page")
        node_types[kind] = node_types.get(kind, 0) + 1

    print("\n  Node types:")
    for kind, count in sorted(node_types.items()):
        print(f"    {kind}: {count}")

    # Show example nodes and edges
    print("\n  Example nodes:")
    for node in graph_data["nodes"][:5]:
        print(f"    - {node['label']} ({node['domain']})")

    print("\n  Example edges:")
    for edge in graph_data["edges"][:5]:
        print(f"    - {edge['source']} -> {edge['target']}")

# Example 4: Generate XML sitemap
print("\n\n=== Sitemap Export ===")
sitemap_exporter = SitemapExporter(wiki_base=wiki_base)

sitemap_path = sitemap_exporter.export(output_file=exports_dir / "sitemap.xml")
print(f"Sitemap exported to: {sitemap_path}")

if sitemap_path.exists():
    sitemap_content = sitemap_path.read_text()
    lines = sitemap_content.split("\n")[:30]
    print("\nSitemap preview:")
    print("-" * 60)
    print("\n".join(lines))
    print("-" * 60)

# Example 5: Run all exports via job
print("\n\n=== Full Export Job ===")
export_job = ExportJob(wiki_base=wiki_base)
job_stats = export_job.execute()

print("Export job complete!")
print(f"  llms.txt: {job_stats['llmstxt_path']}")
print(f"  JSON sidecars: {job_stats['json_sidecars_count']} files")
print(f"  Graph: {job_stats['graph_path']}")
print(f"  Sitemap: {job_stats['sitemap_path']}")

# Example 6: Use exports in downstream tools
print("\n\n=== Using Exports ===")
print("Export use cases:")
print("\n1. LLM Context (llms.txt):")
print("   - Load into LLM context for question answering")
print("   - Provide as knowledge base for agents")
print("   - Use with RAG systems")
print("\n2. Programmatic Access (JSON sidecars):")
print("   - Build custom visualizations")
print("   - Integrate with other tools")
print("   - Generate static sites")
print("\n3. Graph Analysis (graph.json):")
print("   - Visualize with D3.js, Cytoscape, etc.")
print("   - Find clusters and communities")
print("   - Analyze link structure")
print("\n4. Navigation (sitemap.xml):")
print("   - Generate table of contents")
print("   - Build navigation menus")
print("   - SEO for static sites")
