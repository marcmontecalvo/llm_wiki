"""Command-line interface for llm-wiki."""

import subprocess
from pathlib import Path

import click

from llm_wiki import __version__


@click.group()
@click.version_option(version=__version__)
def main():
    """Federated LLM wiki system with daemon governance."""
    pass


@main.command()
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def init(wiki_base: Path):
    """Initialize a new wiki instance."""
    click.echo(f"Initializing wiki at {wiki_base}...")

    # Run bootstrap script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "bootstrap.sh"

    if not script_path.exists():
        click.echo("Error: bootstrap.sh not found", err=True)
        raise click.Abort()

    try:
        result = subprocess.run(
            ["bash", str(script_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        click.echo(result.stdout)
        click.echo(f"✓ Wiki initialized at {wiki_base}/")
        click.echo("\nNext steps:")
        click.echo("  1. Configure domains in config/domains.yaml")
        click.echo("  2. Add content to wiki_system/inbox/")
        click.echo("  3. Run: llm-wiki daemon")
    except subprocess.CalledProcessError as e:
        click.echo(f"Error: {e.stderr}", err=True)
        raise click.Abort() from e


@main.command()
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="config",
    help="Path to configuration directory",
)
def daemon(config_dir: Path):
    """Start the wiki daemon."""
    from llm_wiki.daemon.main import run_daemon

    click.echo(f"Starting daemon with config from {config_dir}...")
    run_daemon(config_dir)


@main.group()
def search():
    """Search and query wiki content."""
    pass


@search.command("query")
@click.argument("query_text", required=False)
@click.option("--domain", help="Filter by domain")
@click.option("--kind", help="Filter by kind (page, entity, concept)")
@click.option("--tags", multiple=True, help="Filter by tags")
@click.option("--limit", default=10, help="Maximum results to return")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def search_query(
    query_text: str | None,
    domain: str | None,
    kind: str | None,
    tags: tuple[str, ...],
    limit: int,
    wiki_base: Path,
):
    """Search wiki content with optional filters."""
    from llm_wiki.query.search import WikiQuery

    wiki = WikiQuery(wiki_base=wiki_base)

    if query_text:
        results = wiki.search(
            query=query_text,
            domain=domain,
            kind=kind,
            tags=list(tags) if tags else None,
            limit=limit,
        )
    else:
        # Metadata-only query
        if domain:
            results = wiki.find_by_domain(domain)[:limit]
        elif kind:
            results = wiki.find_by_kind(kind)[:limit]
        elif tags:
            all_results = []
            for tag in tags:
                all_results.extend(wiki.find_by_tag(tag))
            # Remove duplicates based on page ID
            seen = set()
            results = []
            for page in all_results:
                if page["id"] not in seen:
                    seen.add(page["id"])
                    results.append(page)
            results = results[:limit]
        else:
            click.echo("Error: Provide query text or filters (--domain, --kind, --tags)")
            raise click.Abort()

    if not results:
        click.echo("No results found.")
        return

    click.echo(f"Found {len(results)} results:\n")
    for i, result in enumerate(results, 1):
        title = result.get("title", "Untitled")
        page_id = result.get("id", "")
        page_domain = result.get("domain", "")
        score = result.get("score", 0.0)

        if score > 0:
            click.echo(f"{i}. {title} ({page_domain}) [score: {score:.3f}]")
        else:
            click.echo(f"{i}. {title} ({page_domain})")

        if "summary" in result:
            click.echo(f"   {result['summary']}")

        click.echo(f"   ID: {page_id}\n")


@search.command("get")
@click.argument("page_id")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def search_get(page_id: str, wiki_base: Path):
    """Get a specific page by ID."""
    from llm_wiki.query.search import WikiQuery

    wiki = WikiQuery(wiki_base=wiki_base)
    page = wiki.get_page(page_id)

    if not page:
        click.echo(f"Error: Page '{page_id}' not found", err=True)
        raise click.Abort()

    click.echo(f"Title: {page.get('title', 'Untitled')}")
    click.echo(f"ID: {page.get('id', '')}")
    click.echo(f"Domain: {page.get('domain', '')}")
    click.echo(f"Kind: {page.get('kind', 'page')}")

    if "tags" in page:
        click.echo(f"Tags: {', '.join(page['tags'])}")

    if "summary" in page:
        click.echo(f"\nSummary: {page['summary']}")

    if "source" in page:
        click.echo(f"Source: {page['source']}")


@main.group()
def ingest():
    """Ingest content into the wiki."""
    pass


@ingest.command("file")
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
@click.option("--domain", help="Target domain (overrides auto-routing)")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def ingest_file(file_path: Path, domain: str | None, wiki_base: Path):
    """Ingest a file into the wiki inbox."""
    import shutil

    inbox = wiki_base / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    dest = inbox / file_path.name
    shutil.copy2(file_path, dest)

    click.echo(f"✓ File copied to inbox: {dest}")
    click.echo(f"  Domain: {domain if domain else 'auto-detect'}")
    click.echo("\nThe daemon will process this file automatically.")


@ingest.command("text")
@click.argument("content")
@click.option("--title", required=True, help="Page title")
@click.option("--domain", default="general", help="Target domain")
@click.option("--tags", multiple=True, help="Tags for the page")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def ingest_text(content: str, title: str, domain: str, tags: tuple[str, ...], wiki_base: Path):
    """Create a page from text content."""
    import re
    from datetime import UTC, datetime

    # Generate page ID from title
    page_id = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

    # Create markdown content
    now = datetime.now(UTC).isoformat()
    frontmatter = f"""---
id: {page_id}
title: {title}
domain: {domain}
created: {now}
updated: {now}"""

    if tags:
        frontmatter += "\ntags:\n"
        for tag in tags:
            frontmatter += f"  - {tag}\n"

    frontmatter += "---\n\n"

    full_content = frontmatter + f"# {title}\n\n{content}\n"

    # Write to inbox
    inbox = wiki_base / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    dest = inbox / f"{page_id}.md"
    dest.write_text(full_content)

    click.echo(f"✓ Page created: {dest}")
    click.echo(f"  ID: {page_id}")
    click.echo(f"  Domain: {domain}")
    click.echo("\nThe daemon will process this page automatically.")


@main.group()
def govern():
    """Run governance checks and maintenance."""
    pass


@govern.command("check")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def govern_check(wiki_base: Path):
    """Run governance checks and generate report."""
    from llm_wiki.daemon.jobs.governance import GovernanceJob

    click.echo("Running governance checks...")

    job = GovernanceJob(wiki_base=wiki_base)
    stats = job.execute()

    click.echo("\n" + "=" * 60)
    click.echo("GOVERNANCE REPORT")
    click.echo("=" * 60)

    click.echo(f"\nTotal pages: {stats.get('total_pages', 0)}")
    click.echo(f"Lint issues: {stats.get('lint_issues', 0)}")
    click.echo(f"  - Errors: {stats.get('lint_errors', 0)}")
    click.echo(f"Stale pages: {stats.get('stale_pages', 0)}")
    click.echo(f"Low quality pages: {stats.get('low_quality_pages', 0)}")

    if "report_path" in stats:
        click.echo(f"\n✓ Full report: {stats['report_path']}")


@govern.command("rebuild-index")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def govern_rebuild_index(wiki_base: Path):
    """Rebuild search indexes."""
    from llm_wiki.daemon.jobs.index_rebuild import IndexRebuildJob

    click.echo("Rebuilding indexes...")

    job = IndexRebuildJob(wiki_base=wiki_base)
    stats = job.execute()

    click.echo(f"\n✓ Metadata index: {stats.get('metadata_pages', 0)} pages")
    click.echo(f"✓ Fulltext index: {stats.get('fulltext_documents', 0)} documents")


@main.group()
def export():
    """Export wiki content in various formats."""
    pass


@export.command("all")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def export_all(wiki_base: Path):
    """Export all formats (llms.txt, graph, sitemap, JSON sidecars)."""
    from llm_wiki.daemon.jobs.export import ExportJob

    click.echo("Exporting all formats...")

    job = ExportJob(wiki_base=wiki_base)
    stats = job.execute()

    click.echo("\n" + "=" * 60)
    click.echo("EXPORT COMPLETE")
    click.echo("=" * 60)

    if "llmstxt_path" in stats:
        click.echo(f"\n✓ llms.txt: {stats['llmstxt_path']}")

    if "json_sidecars_count" in stats:
        click.echo(f"✓ JSON sidecars: {stats['json_sidecars_count']} files")

    if "graph_path" in stats:
        click.echo(f"✓ Graph: {stats['graph_path']}")

    if "sitemap_path" in stats:
        click.echo(f"✓ Sitemap: {stats['sitemap_path']}")


@export.command("llmstxt")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (default: wiki_system/exports/llms.txt)",
)
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def export_llmstxt(output: Path | None, wiki_base: Path):
    """Export to llms.txt format for LLM consumption."""
    from llm_wiki.export.llmstxt import LLMSTxtExporter

    exporter = LLMSTxtExporter(wiki_base=wiki_base)

    if output:
        result = exporter.export_all(output_file=output)
    else:
        exports_dir = wiki_base / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        result = exporter.export_all(output_file=exports_dir / "llms.txt")

    click.echo(f"✓ Exported to: {result}")


@export.command("graph")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (default: wiki_system/exports/graph.json)",
)
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def export_graph(output: Path | None, wiki_base: Path):
    """Export graph of page relationships."""
    from llm_wiki.export.graph import GraphExporter

    exporter = GraphExporter(wiki_base=wiki_base)

    if output:
        result = exporter.export_json(output_file=output)
    else:
        exports_dir = wiki_base / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        result = exporter.export_json(output_file=exports_dir / "graph.json")

    click.echo(f"✓ Exported to: {result}")


if __name__ == "__main__":
    main()
