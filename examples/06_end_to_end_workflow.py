"""
End-to-End Workflow

This example demonstrates a complete workflow from ingestion to export,
showing how all components work together.
"""

import json
from pathlib import Path

from llm_wiki.daemon.jobs.export import ExportJob
from llm_wiki.daemon.jobs.governance import GovernanceJob
from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob
from llm_wiki.query.search import WikiQuery

# Setup
wiki_base = Path("wiki_system")
inbox = wiki_base / "inbox"

print("=== End-to-End Wiki Workflow ===\n")

# Step 1: Add content to inbox
print("Step 1: Adding content to inbox")
print("-" * 60)

content1 = """---
title: Test-Driven Development
domain: tech
tags:
  - testing
  - tdd
  - best-practices
---

# Test-Driven Development

Test-Driven Development (TDD) is a software development approach where tests
are written before the actual code.

## The TDD Cycle

1. **Red**: Write a failing test
2. **Green**: Write minimal code to pass the test
3. **Refactor**: Improve the code while keeping tests passing

## Benefits

- Better code design
- Higher test coverage
- Fewer bugs
- Living documentation
- Confidence to refactor

Source: https://martinfowler.com/bliki/TestDrivenDevelopment.html
"""

file1 = inbox / "test-driven-development.md"
file1.write_text(content1)
print(f"Created: {file1.name}")

content2 = """---
title: Continuous Integration
domain: tech
tags:
  - ci-cd
  - devops
  - automation
---

# Continuous Integration

Continuous Integration (CI) is the practice of frequently merging code changes
into a central repository, followed by automated builds and tests.

## Key Practices

- Commit code frequently
- Maintain a single source repository
- Automate the build
- Make builds self-testing
- Keep the build fast
- Test in a clone of production
- Make it easy to get latest deliverables

## Popular CI Tools

- Jenkins
- GitHub Actions
- GitLab CI
- CircleCI
- Travis CI

Source: https://www.martinfowler.com/articles/continuousIntegration.html
"""

file2 = inbox / "continuous-integration.md"
file2.write_text(content2)
print(f"Created: {file2.name}")

# Note: In production, the InboxWatcher daemon would process these automatically
# For this example, we'll simulate by manually moving files

print("\n(In production, InboxWatcher daemon would process these files)")

# Step 2: Rebuild indexes
print("\n\nStep 2: Rebuilding indexes")
print("-" * 60)

index_job = IndexRebuildJob(wiki_base=wiki_base)
index_stats = index_job.execute()

print("Metadata index rebuilt:")
print(f"  Total pages: {index_stats['metadata_pages']}")
print(f"  Unique tags: {index_stats['metadata_tags']}")
print(f"  Domains: {index_stats['metadata_domains']}")
print("\nFulltext index rebuilt:")
print(f"  Documents indexed: {index_stats['fulltext_documents']}")
print(f"  Vocabulary size: {index_stats['fulltext_vocabulary']}")

# Step 3: Search for content
print("\n\nStep 3: Searching wiki content")
print("-" * 60)

wiki = WikiQuery(wiki_base=wiki_base)

# Search 1: Find testing-related pages
results = wiki.search(query="testing automation", domain="tech", limit=5)
print("\nSearch: 'testing automation' in tech domain")
print(f"Found {len(results)} results:")
for result in results:
    score = result.get("score", 0.0)
    print(f"  - {result['title']} (score: {score:.3f})")

# Search 2: Find by tag
tdd_pages = wiki.find_by_tag("tdd")
print(f"\nPages tagged 'tdd': {len(tdd_pages)}")
for page_id in tdd_pages:
    page = wiki.get_page(page_id)
    if page:
        print(f"  - {page['title']}")

# Search 3: Find by tag
devops_pages = wiki.find_by_tag("devops")
print(f"\nPages tagged 'devops': {len(devops_pages)}")
for page_id in devops_pages:
    page = wiki.get_page(page_id)
    if page:
        print(f"  - {page['title']}")

# Step 4: Run governance checks
print("\n\nStep 4: Running governance checks")
print("-" * 60)

governance_job = GovernanceJob(wiki_base=wiki_base)
gov_stats = governance_job.execute()

print("Governance check complete:")
print(f"  Total pages: {gov_stats['total_pages']}")
print(f"  Lint issues: {gov_stats['lint_issues']}")
print(f"  Lint errors: {gov_stats['lint_errors']}")
print(f"  Stale pages: {gov_stats['stale_pages']}")
print(f"  Low quality pages: {gov_stats['low_quality_pages']}")
print(f"  Report: {gov_stats['report_path']}")

# Step 5: Export content
print("\n\nStep 5: Exporting wiki content")
print("-" * 60)

export_job = ExportJob(wiki_base=wiki_base)
export_stats = export_job.execute()

print("Export complete:")
print(f"  llms.txt: {export_stats['llmstxt_path']}")
print(f"  JSON sidecars: {export_stats['json_sidecars_count']} files")
print(f"  Graph: {export_stats['graph_path']}")
print(f"  Sitemap: {export_stats['sitemap_path']}")

# Step 6: Use exports
print("\n\nStep 6: Using exports")
print("-" * 60)

# Read llms.txt
llmstxt_path = Path(export_stats["llmstxt_path"])
if llmstxt_path.exists():
    content = llmstxt_path.read_text()
    print(f"\nllms.txt size: {len(content)} characters")
    print("Preview (first 30 lines):")
    lines = content.split("\n")[:30]
    for line in lines:
        print(f"  {line}")
    print("  ...")

# Read graph
graph_path = Path(export_stats["graph_path"])
if graph_path.exists():
    graph = json.loads(graph_path.read_text())
    print("\nGraph statistics:")
    print(f"  Nodes: {len(graph['nodes'])}")
    print(f"  Edges: {len(graph['edges'])}")

    # Find pages that link to our new pages
    tdd_links = [e for e in graph["edges"] if e["target"] == "test-driven-development"]
    ci_links = [e for e in graph["edges"] if e["target"] == "continuous-integration"]

    print(f"\nPages linking to Test-Driven Development: {len(tdd_links)}")
    print(f"Pages linking to Continuous Integration: {len(ci_links)}")

# Summary
print("\n\n" + "=" * 60)
print("WORKFLOW SUMMARY")
print("=" * 60)
print("""
This end-to-end workflow demonstrated:

1. ✓ Content ingestion via inbox
2. ✓ Index building for fast search
3. ✓ Fulltext and metadata search
4. ✓ Quality governance and maintenance
5. ✓ Export to multiple formats

In a production deployment:
- InboxWatcher daemon monitors inbox/ continuously
- Indexes rebuild automatically on schedule
- Governance checks run periodically
- Exports update regularly
- Agents query via WikiQuery API or /wiki skill

The wiki is now fully operational and ready for:
- Agent knowledge management
- Documentation centralization
- Research organization
- Knowledge sharing
""")
