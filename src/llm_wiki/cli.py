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
@click.option(
    "--with-contradictions",
    is_flag=True,
    help="Include contradiction detection (requires LLM client)",
)
def govern_check(wiki_base: Path, with_contradictions: bool):
    """Run governance checks and generate report."""
    from llm_wiki.daemon.jobs.governance import GovernanceJob

    click.echo("Running governance checks...")

    client = None
    if with_contradictions:
        try:
            from llm_wiki.models.client import create_model_client
            from llm_wiki.models.config import ModelProviderConfig

            # Create default config for local LLM
            config = ModelProviderConfig(
                provider="ollama",
                model="llama3.2:3b",
            )
            client = create_model_client(config)
            click.echo("Using LLM client for contradiction detection...")
        except Exception as e:
            click.echo(f"Warning: Could not initialize LLM client: {e}", err=True)

    job = GovernanceJob(wiki_base=wiki_base, client=client)
    stats = job.execute()

    click.echo("\n" + "=" * 60)
    click.echo("GOVERNANCE REPORT")
    click.echo("=" * 60)

    click.echo(f"\nTotal pages: {stats.get('total_pages', 0)}")
    click.echo(f"Lint issues: {stats.get('lint_issues', 0)}")
    click.echo(f"  - Errors: {stats.get('lint_errors', 0)}")
    click.echo(f"Stale pages: {stats.get('stale_pages', 0)}")
    click.echo(f"Low quality pages: {stats.get('low_quality_pages', 0)}")

    if stats.get("contradictions", 0) > 0:
        click.echo(f"Contradictions found: {stats['contradictions']}")

    if "report_path" in stats:
        click.echo(f"\n✓ Full report: {stats['report_path']}")


@govern.command("contradictions")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option(
    "--min-confidence",
    type=float,
    default=0.6,
    help="Minimum confidence threshold (0.0-1.0)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file for report (defaults to wiki_system/reports/)",
)
def govern_contradictions(wiki_base: Path, min_confidence: float, output: Path | None):
    """Detect and report contradictions across pages."""
    from llm_wiki.governance.contradictions import ContradictionDetector
    from llm_wiki.models.client import create_model_client
    from llm_wiki.models.config import ModelProviderConfig

    click.echo("Detecting contradictions in wiki...")

    try:
        # Create default config for local LLM
        config = ModelProviderConfig(
            provider="ollama",
            model="llama3.2:3b",
        )
        client = create_model_client(config)
        detector = ContradictionDetector(client=client, min_confidence=min_confidence)

        report = detector.analyze_all_pages(wiki_base)

        click.echo(f"\n✓ Detected {report.total_contradictions} potential contradictions")
        click.echo(f"  - High confidence: {len(report.high_confidence)}")
        click.echo(f"  - Medium confidence: {len(report.medium_confidence)}")
        click.echo(f"  - Low confidence: {len(report.low_confidence)}")

        # Generate report
        if output:
            report_path = output
        else:
            from datetime import UTC, datetime

            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            report_path = wiki_base / "reports" / f"contradictions_{timestamp}.md"

        detector.generate_report(report, report_path)

        click.echo(f"\n✓ Report saved: {report_path}")

        # Print high confidence contradictions
        if report.high_confidence:
            click.echo("\nHigh Confidence Contradictions:")
            for contradiction in report.high_confidence[:10]:
                click.echo(f"\n  {contradiction.page_id_1} vs {contradiction.page_id_2}")
                click.echo(f"    Confidence: {contradiction.confidence:.2f}")
                click.echo(f"    Type: {contradiction.contradiction_type}")
                click.echo(f"    Claim 1: {contradiction.claim_1.claim[:60]}...")
                click.echo(f"    Claim 2: {contradiction.claim_2.claim[:60]}...")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort() from e


@govern.command("duplicates")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option(
    "--min-score",
    type=float,
    default=0.3,
    help="Minimum duplicate score threshold (0.0-1.0)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file for report (defaults to wiki_system/reports/)",
)
def govern_duplicates(wiki_base: Path, min_score: float, output: Path | None):
    """Detect and report duplicate entity pages."""
    from llm_wiki.governance.duplicates import DuplicateDetector

    click.echo("Detecting duplicate entities in wiki...")

    try:
        detector = DuplicateDetector(min_score=min_score, wiki_base=wiki_base)
        report = detector.analyze_all_pages(wiki_base)

        click.echo(f"\n✓ Detected {report.total_candidates} potential duplicates")
        click.echo(f"  - High confidence: {len(report.high_confidence)}")
        click.echo(f"  - Medium confidence: {len(report.medium_confidence)}")
        click.echo(f"  - Low confidence: {len(report.low_confidence)}")

        # Generate report
        if output:
            report_path = output
        else:
            from datetime import UTC, datetime

            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            report_path = wiki_base / "reports" / f"duplicates_{timestamp}.md"

        detector.generate_report(report, report_path)

        click.echo(f"\n✓ Report saved: {report_path}")

        # Print high confidence duplicates
        if report.high_confidence:
            click.echo("\nHigh Confidence Duplicates:")
            for candidate in report.high_confidence[:10]:
                click.echo(f"\n  {candidate.page_1} ↔ {candidate.page_2}")
                click.echo(f"    Score: {candidate.duplicate_score:.3f}")
                click.echo(f"    Action: {candidate.suggested_action}")
                click.echo(f"    Reasons: {', '.join(candidate.reasons[:2])}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort() from e


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


@export.command("llmsfull")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (default: wiki_system/exports/llms-full.txt)",
)
@click.option(
    "--domain",
    type=str,
    help="Export specific domain only",
)
@click.option(
    "--min-quality",
    type=float,
    default=0.0,
    help="Minimum quality/confidence score to include (0.0-1.0)",
)
@click.option(
    "--max-pages",
    type=int,
    help="Maximum number of pages to export",
)
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def export_llmsfull(
    output: Path | None,
    domain: str | None,
    min_quality: float,
    max_pages: int | None,
    wiki_base: Path,
):
    """Export to llms-full.txt format with comprehensive page data."""
    from llm_wiki.export.llmsfull import LLMSFullExporter

    exporter = LLMSFullExporter(wiki_base=wiki_base)

    # Show stats
    stats = exporter.get_export_stats()
    click.echo(
        f"Wiki contains {stats['total_pages']} pages across {stats['total_domains']} domains"
    )
    click.echo(f"  - {stats['pages_with_extractions']} pages have extracted data")
    click.echo(f"  - {stats['pages_with_backlinks']} pages have backlinks")
    click.echo()

    # Determine output file
    if not output:
        exports_dir = wiki_base / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        if domain:
            output = exports_dir / f"{domain}_llms-full.txt"
        else:
            output = exports_dir / "llms-full.txt"

    # Execute export
    if domain:
        click.echo(f"Exporting domain '{domain}'...")
        result = exporter.export_domain(
            domain, output_file=output, min_quality=min_quality, max_pages=max_pages
        )
    else:
        click.echo("Exporting all domains...")
        result = exporter.export_all(
            output_file=output, min_quality=min_quality, max_pages=max_pages
        )

    # Show results
    file_size = result.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    click.echo(f"✓ Exported to: {result}")
    click.echo(f"  File size: {file_size_mb:.2f} MB ({file_size:,} bytes)")


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


@main.group()
def promote():
    """Manage page promotion to shared space."""
    pass


@promote.command("check")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def promote_check(wiki_base: Path):
    """Check for pages eligible for promotion."""
    from llm_wiki.promotion.engine import PromotionEngine

    click.echo("Scanning for promotion candidates...")

    engine = PromotionEngine(wiki_base=wiki_base)
    candidates = engine.find_candidates()

    click.echo(f"\nFound {len(candidates)} promotion candidates:")
    click.echo("=" * 80)

    if not candidates:
        click.echo("No candidates found.")
        return

    for i, candidate in enumerate(candidates[:20], 1):
        click.echo(f"\n{i}. {candidate.title} (ID: {candidate.page_id})")
        click.echo(f"   Domain: {candidate.domain}")
        click.echo(f"   Score: {candidate.promotion_score:.2f}")
        click.echo(f"   Cross-domain refs: {candidate.cross_domain_references}")
        click.echo(f"   Referring domains: {', '.join(sorted(candidate.referring_domains))}")
        click.echo(f"   Quality: {candidate.quality_score:.2f}")
        click.echo("   Status: ", nl=False)

        if candidate.should_auto_promote:
            click.echo("Ready for auto-promotion")
        elif candidate.should_suggest_promote:
            click.echo("Eligible for review")
        else:
            click.echo("Below threshold")

    if len(candidates) > 20:
        click.echo(f"\n... and {len(candidates) - 20} more")

    click.echo(f"\nTotal: {len(candidates)} candidates")


@promote.command("process")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate promotion without making changes",
)
def promote_process(wiki_base: Path, dry_run: bool):
    """Process all promotion candidates."""
    from llm_wiki.promotion.engine import PromotionEngine

    mode = "Simulating" if dry_run else "Processing"
    click.echo(f"{mode} promotion candidates...")

    engine = PromotionEngine(wiki_base=wiki_base)
    report = engine.process_candidates()

    click.echo("\n" + "=" * 60)
    click.echo("PROMOTION REPORT")
    click.echo("=" * 60)

    click.echo(f"\nTotal candidates: {report.total_candidates}")
    click.echo(f"Auto-promoted: {report.auto_promoted}")
    click.echo(f"Suggested for review: {report.suggested_for_review}")

    if report.promotion_results:
        click.echo("\nPromoted pages:")
        for result in report.promotion_results:
            status = "✓" if result.success else "✗"
            click.echo(f"  {status} {result.page_id}: {result.message}")

    click.echo("\n✓ Report saved to wiki_system/reports/")


@promote.command("promote")
@click.argument("page_id")
@click.option(
    "--domain",
    required=True,
    help="Source domain of the page",
)
@click.option(
    "--update-refs",
    is_flag=True,
    default=True,
    help="Update all references to point to shared",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Simulate promotion without making changes",
)
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def promote_page(page_id: str, domain: str, update_refs: bool, dry_run: bool, wiki_base: Path):
    """Promote a specific page to shared."""
    from llm_wiki.promotion.engine import PromotionEngine

    click.echo(f"Promoting {page_id} from {domain}...")

    engine = PromotionEngine(wiki_base=wiki_base)
    result = engine.promote_page(page_id, domain, update_references=update_refs, dry_run=dry_run)

    if result.success:
        click.echo(f"✓ {result.message}")
        if result.shared_location:
            click.echo(f"  Location: {result.shared_location}")
        if result.references_updated > 0:
            click.echo(f"  Updated {result.references_updated} references")
    else:
        click.echo(f"✗ {result.message}", err=True)


@promote.command("unpromote")
@click.argument("page_id")
@click.option(
    "--domain",
    required=True,
    help="Target domain to move page back to",
)
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def unpromote_page(page_id: str, domain: str, wiki_base: Path):
    """Un-promote a page from shared back to domain-local."""
    from llm_wiki.promotion.engine import PromotionEngine

    click.echo(f"Un-promoting {page_id} back to {domain}...")

    engine = PromotionEngine(wiki_base=wiki_base)
    result = engine.unpromote_page(page_id, domain)

    if result.success:
        click.echo(f"✓ {result.message}")
        if result.shared_location:
            click.echo(f"  Location: {result.shared_location}")
    else:
        click.echo(f"✗ {result.message}", err=True)


if __name__ == "__main__":
    main()
