"""
Search and Query Workflow

This example demonstrates how to search and query the wiki system
using the unified query interface.
"""

from pathlib import Path

from llm_wiki.query.search import WikiQuery

# Setup
wiki_base = Path("wiki_system")
wiki = WikiQuery(wiki_base=wiki_base)

# Example 1: Simple fulltext search
print("=== Fulltext Search ===")
results = wiki.search(query="python programming", limit=5)

for result in results:
    print(f"\n{result['title']} ({result['domain']})")
    print(f"  ID: {result['id']}")
    print(f"  Score: {result.get('score', 0.0):.3f}")
    if "summary" in result:
        print(f"  Summary: {result['summary']}")

# Example 2: Search with domain filter
print("\n\n=== Domain-Filtered Search ===")
tech_results = wiki.search(query="programming", domain="tech", limit=10)

print(f"Found {len(tech_results)} results in 'tech' domain:")
for result in tech_results:
    print(f"  - {result['title']}")

# Example 3: Search by tags
print("\n\n=== Tag-Based Search ===")
python_pages = wiki.find_by_tag("python")

print(f"Found {len(python_pages)} pages tagged 'python':")
for page_id in python_pages:
    page = wiki.get_page(page_id)
    if page:
        print(f"  - {page.get('title', 'Untitled')} ({page.get('domain', 'unknown')})")

# Example 4: Search by kind
print("\n\n=== Kind-Based Search ===")
entities = wiki.find_by_kind("entity")

print(f"Found {len(entities)} entity pages:")
for page_id in list(entities)[:10]:  # Show first 10
    page = wiki.get_page(page_id)
    if page:
        print(f"  - {page.get('title', 'Untitled')}")

# Example 5: Combined search (fulltext + filters)
print("\n\n=== Combined Search ===")
results = wiki.search(
    query="docker containers",
    domain="tech",
    kind="entity",
    tags=["containers"],
    limit=5,
)

print("Docker container entities in tech domain:")
for result in results:
    print(f"  - {result['title']} (score: {result.get('score', 0.0):.3f})")

# Example 6: Get specific page
print("\n\n=== Get Specific Page ===")
page = wiki.get_page("python-programming")

if page:
    print(f"Title: {page.get('title')}")
    print(f"Domain: {page.get('domain')}")
    print(f"Kind: {page.get('kind', 'page')}")
    print(f"Tags: {', '.join(page.get('tags', []))}")
    print(f"Summary: {page.get('summary', 'No summary')}")
else:
    print("Page not found")

# Example 7: Find all pages in a domain
print("\n\n=== All Pages in Domain ===")
tech_pages = wiki.find_by_domain("tech")

print(f"Total pages in 'tech' domain: {len(tech_pages)}")
print("First 10:")
for page_id in list(tech_pages)[:10]:
    page = wiki.get_page(page_id)
    if page:
        print(f"  - {page.get('title', 'Untitled')}")
