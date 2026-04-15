"""Example: Using the comprehensive llms-full.txt export."""

from pathlib import Path

from llm_wiki.export.llmsfull import LLMSFullExporter


def main():
    """Demonstrate llms-full.txt export capabilities."""

    # Initialize exporter
    wiki_base = Path("wiki_system")
    exporter = LLMSFullExporter(wiki_base=wiki_base)

    print("=" * 70)
    print("LLMs-Full Export Example")
    print("=" * 70)
    print()

    # Example 1: Get export statistics
    print("1. Wiki Statistics:")
    print("-" * 70)
    stats = exporter.get_export_stats()
    print(f"   Total pages: {stats['total_pages']}")
    print(f"   Total domains: {stats['total_domains']}")
    print(f"   Pages with extractions: {stats['pages_with_extractions']}")
    print(f"   Pages with backlinks: {stats['pages_with_backlinks']}")
    print()

    # Example 2: Export all pages
    print("2. Export All Pages:")
    print("-" * 70)
    print("   Exporting all pages to llms-full.txt...")
    output = exporter.export_all()
    file_size_mb = output.stat().st_size / (1024 * 1024)
    print(f"   ✓ Exported to: {output}")
    print(f"   File size: {file_size_mb:.2f} MB")
    print()

    # Example 3: Export with quality filter
    print("3. Export with Quality Filter (confidence >= 0.8):")
    print("-" * 70)
    print("   Exporting high-confidence pages only...")
    output = exporter.export_all(min_quality=0.8)
    file_size_mb = output.stat().st_size / (1024 * 1024)
    print(f"   ✓ Exported to: {output}")
    print(f"   File size: {file_size_mb:.2f} MB")
    print()

    # Example 4: Export specific domain
    if (wiki_base / "domains").exists():
        domains = [d.name for d in (wiki_base / "domains").iterdir() if d.is_dir()]
        if domains:
            domain = domains[0]
            print(f"4. Export Specific Domain ({domain}):")
            print("-" * 70)
            print(f"   Exporting '{domain}' domain...")
            output = exporter.export_domain(domain)
            file_size_mb = output.stat().st_size / (1024 * 1024)
            print(f"   ✓ Exported to: {output}")
            print(f"   File size: {file_size_mb:.2f} MB")
            print()

    # Example 5: Export with page limit
    print("5. Export with Page Limit (max 100 pages):")
    print("-" * 70)
    print("   Exporting first 100 pages only...")
    output = exporter.export_all(max_pages=100)
    file_size_mb = output.stat().st_size / (1024 * 1024)
    print(f"   ✓ Exported to: {output}")
    print(f"   File size: {file_size_mb:.2f} MB")
    print()

    # Example 6: Export single page
    print("6. Export Single Page:")
    print("-" * 70)
    pages_dir = wiki_base / "domains"
    if pages_dir.exists():
        for domain_dir in pages_dir.iterdir():
            if domain_dir.is_dir():
                pages_subdir = domain_dir / "pages"
                if pages_subdir.exists():
                    page_files = list(pages_subdir.glob("*.md"))
                    if page_files:
                        page_file = page_files[0]
                        print(f"   Exporting page: {page_file.stem}...")
                        page_content = exporter.export_page(page_file)
                        lines = page_content.split("\n")
                        print(f"   ✓ Page exported ({len(lines)} lines)")
                        print()
                        print("   First 300 characters:")
                        print("   " + "-" * 66)
                        print("   " + page_content[:300].replace("\n", "\n   "))
                        break
                break  # Exit outer loop after finding first page

    print()
    print("=" * 70)
    print("Export Examples Complete")
    print("=" * 70)
    print()
    print("For more information, see:")
    print("  - docs/export/llms-full-txt.md (Format documentation)")
    print("  - Run: llm-wiki export llmsfull --help (CLI help)")


if __name__ == "__main__":
    main()
