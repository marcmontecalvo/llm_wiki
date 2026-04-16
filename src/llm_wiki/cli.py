"""Command-line interface for llm-wiki."""

import subprocess
from datetime import UTC
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


@main.group(invoke_without_command=True)
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="config",
    help="Path to configuration directory",
)
@click.pass_context
def daemon(ctx: click.Context, config_dir: Path):
    """Start the wiki daemon, or manage daemon jobs.

    When called without a subcommand, starts the daemon (backwards-compatible
    with the original ``llm-wiki daemon`` invocation).
    """
    # Store config_dir so subcommands can reach it if ever needed
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir
    if ctx.invoked_subcommand is None:
        from llm_wiki.daemon.main import run_daemon

        click.echo(f"Starting daemon with config from {config_dir}...")
        run_daemon(config_dir)


@daemon.command("start")
@click.option(
    "--config-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="config",
    help="Path to configuration directory",
)
def daemon_start(config_dir: Path):
    """Start the wiki daemon (explicit subcommand form)."""
    from llm_wiki.daemon.main import run_daemon

    click.echo(f"Starting daemon with config from {config_dir}...")
    run_daemon(config_dir)


@daemon.command("status")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def daemon_status(wiki_base: Path):
    """Show daemon status and recent job execution summary."""
    from llm_wiki.daemon.execution_store import JobExecutionStore

    store = JobExecutionStore(state_dir=wiki_base / "state" / "job_executions")
    jobs = store.list_jobs()

    if not jobs:
        click.echo("No job execution history found.")
        return

    click.echo(f"Job execution summary (from {wiki_base}/state/job_executions/):\n")
    stats = store.export_stats()
    for job_name, info in sorted(stats.items()):
        last_status = info.get("last_status") or "never run"
        last_started = info.get("last_started_at") or "-"
        total = info.get("total_executions", 0)
        failures = info.get("failures_last_hour", 0)
        duration = info.get("last_duration_seconds")
        duration_str = f"{duration:.1f}s" if duration is not None else "-"

        status_indicator = {
            "completed": "✓",
            "failed": "✗",
            "running": "~",
            "timeout": "!",
            "retrying": "↺",
            "cancelled": "-",
        }.get(last_status, "?")

        click.echo(f"  {status_indicator} {job_name}")
        click.echo(f"      last status : {last_status}")
        click.echo(f"      last started: {last_started}")
        click.echo(f"      last runtime: {duration_str}")
        click.echo(f"      total runs  : {total}  (failures last hour: {failures})")
        click.echo()


@daemon.group("jobs")
def daemon_jobs():
    """Inspect and manage individual daemon jobs."""
    pass


@daemon_jobs.command("list")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def daemon_jobs_list(wiki_base: Path):
    """List all jobs that have execution history."""
    from llm_wiki.daemon.execution_store import JobExecutionStore

    store = JobExecutionStore(state_dir=wiki_base / "state" / "job_executions")
    jobs = store.list_jobs()

    if not jobs:
        click.echo("No job execution history found.")
        return

    click.echo(f"{'Job name':<40}  {'Last status':<12}  {'Total runs':>10}  {'Fails/hr':>8}")
    click.echo("-" * 76)
    stats = store.export_stats()
    for job_name in sorted(jobs):
        info = stats.get(job_name, {})
        last_status = info.get("last_status") or "never"
        total = info.get("total_executions", 0)
        failures = info.get("failures_last_hour", 0)
        click.echo(f"{job_name:<40}  {last_status:<12}  {total:>10}  {failures:>8}")


@daemon_jobs.command("history")
@click.argument("job_name")
@click.option("--limit", default=20, help="Maximum entries to show")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def daemon_jobs_history(job_name: str, limit: int, wiki_base: Path):
    """Show execution history for a specific job."""
    from llm_wiki.daemon.execution_store import JobExecutionStore

    store = JobExecutionStore(state_dir=wiki_base / "state" / "job_executions")
    history = store.get_history(job_name)

    if not history.executions:
        click.echo(f"No execution history for job '{job_name}'.")
        return

    click.echo(f"Execution history for '{job_name}' (showing up to {limit}):\n")
    executions = list(reversed(history.executions))[:limit]

    for ex in executions:
        started = ex.started_at.strftime("%Y-%m-%d %H:%M:%S")
        duration = f"{ex.duration_seconds:.1f}s" if ex.duration_seconds else "-"
        status = ex.status.value
        indicator = {
            "completed": "✓",
            "failed": "✗",
            "running": "~",
            "timeout": "!",
        }.get(status, "?")

        click.echo(
            f"  {indicator} [{started}]  {status:<12}  {duration:>8}  (id: {ex.execution_id[:8]})"
        )
        if ex.error:
            click.echo(f"      error: {ex.error}")


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


@search.command("backlinks")
@click.argument("page_id")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def search_backlinks(page_id: str, wiki_base: Path):
    """Show all pages that link to a given page."""
    from llm_wiki.index.backlinks import BacklinkIndex

    index = BacklinkIndex(index_dir=wiki_base / "index")
    index.load()

    if page_id not in index.index:
        click.echo(f"Page '{page_id}' not found in backlink index.")
        click.echo("Run 'llm-wiki govern rebuild-index' to refresh the index.")
        return

    backlinks = index.get_backlinks(page_id)
    forward_links = index.get_forward_links(page_id)
    broken_links = index.get_broken_links(page_id)

    click.echo(f"Link information for: {page_id}\n")

    if backlinks:
        click.echo(f"Backlinks ({len(backlinks)} pages link here):")
        for src in backlinks:
            click.echo(f"  <- {src}")
    else:
        click.echo("Backlinks: none (orphan page)")

    if forward_links:
        click.echo(f"\nForward links ({len(forward_links)} outgoing):")
        for tgt in forward_links:
            click.echo(f"  -> {tgt}")

    if broken_links:
        click.echo(f"\nBroken links ({len(broken_links)} unresolved):")
        for broken in broken_links:
            click.echo(f"  !! {broken}")


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


@ingest.command("stats")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def ingest_stats(wiki_base: Path):
    """Show ingestion statistics including failed files."""
    from llm_wiki.ingest.failed import FailedIngestionsTracker

    state_dir = wiki_base / "state"
    tracker = FailedIngestionsTracker(state_dir=state_dir)
    stats = tracker.get_stats()

    click.echo("Ingestion Statistics")
    click.echo("=" * 40)
    click.echo(f"Total failed:        {stats['total_failed']}")
    click.echo(f"Permanent failures:  {stats['permanent_failures']}")
    click.echo(f"Transient failures:  {stats['transient_failures']}")
    click.echo(f"Retryable now:       {stats['retryable_now']}")

    if stats["by_reason"]:
        click.echo("\nFailures by reason:")
        for reason, count in sorted(stats["by_reason"].items()):
            click.echo(f"  {reason}: {count}")


@ingest.group("failed")
def ingest_failed():
    """Manage failed ingestions."""
    pass


@ingest_failed.command("list")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option("--permanent-only", is_flag=True, help="Show only permanently failed files")
def ingest_failed_list(wiki_base: Path, permanent_only: bool):
    """List failed ingestions."""
    from llm_wiki.ingest.failed import FailedIngestionsTracker

    state_dir = wiki_base / "state"
    tracker = FailedIngestionsTracker(state_dir=state_dir)

    ingestions = tracker.get_permanent_failures() if permanent_only else tracker.get_all_failed()

    if not ingestions:
        click.echo("No failed ingestions.")
        return

    click.echo(f"{'File':<40} {'Reason':<25} {'Count':>5}  {'Status':<12}  Next Retry")
    click.echo("-" * 110)
    for ing in sorted(ingestions, key=lambda i: i.file_path.name):
        status = "permanent" if ing.permanent_failure else "retryable"
        next_retry = "—" if ing.permanent_failure else ing.next_retry.strftime("%Y-%m-%d %H:%M")
        click.echo(
            f"{ing.file_path.name:<40} {ing.failure_reason:<25} {ing.failure_count:>5}  {status:<12}  {next_retry}"
        )


@ingest_failed.command("retry")
@click.argument("file_path", type=click.Path(path_type=Path))
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def ingest_failed_retry(file_path: Path, wiki_base: Path):
    """Manually retry a failed ingestion by moving it back to the inbox queue."""
    import shutil

    from llm_wiki.ingest.failed import FailedIngestionsTracker
    from llm_wiki.ingest.watcher import InboxWatcher

    state_dir = wiki_base / "state"
    tracker = FailedIngestionsTracker(state_dir=state_dir)
    watcher = InboxWatcher(inbox_dir=wiki_base / "inbox")

    failed_path = watcher.failed_dir / file_path.name
    if not failed_path.exists():
        if file_path.exists():
            failed_path = file_path
        else:
            click.echo(f"Error: File not found in failed directory: {file_path.name}", err=True)
            raise click.Abort()

    new_path = watcher.new_dir / failed_path.name
    if new_path.exists():
        counter = 1
        while (watcher.new_dir / f"{failed_path.stem}_{counter}{failed_path.suffix}").exists():
            counter += 1
        new_path = watcher.new_dir / f"{failed_path.stem}_{counter}{failed_path.suffix}"

    shutil.move(str(failed_path), str(new_path))

    error_file = failed_path.with_suffix(failed_path.suffix + ".error")
    if error_file.exists():
        error_file.unlink()

    # Clear using failed_path (the key the tracker recorded the failure under)
    tracker.clear_ingestion(failed_path)

    click.echo(f"✓ Queued for retry: {new_path.name}")
    click.echo("  The daemon will pick it up on the next inbox scan.")


@ingest_failed.command("abandon")
@click.argument("file_path", type=click.Path(path_type=Path))
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def ingest_failed_abandon(file_path: Path, wiki_base: Path, yes: bool):
    """Mark a failed ingestion as permanently abandoned (no more retries)."""
    from llm_wiki.ingest.failed import FailedIngestionsTracker

    state_dir = wiki_base / "state"
    tracker = FailedIngestionsTracker(state_dir=state_dir)

    ingestion = tracker.get_failed_ingestion(file_path)
    if ingestion is None:
        all_failed = tracker.get_all_failed()
        matches = [i for i in all_failed if i.file_path.name == file_path.name]
        if not matches:
            click.echo(f"Error: No failure record found for: {file_path.name}", err=True)
            raise click.Abort()
        if len(matches) > 1:
            click.echo(
                f"Error: Multiple records match '{file_path.name}'. Specify the full path:",
                err=True,
            )
            for m in matches:
                click.echo(f"  {m.file_path}", err=True)
            raise click.Abort()
        ingestion = matches[0]
        file_path = ingestion.file_path

    if not yes:
        click.confirm(
            f"Permanently abandon '{ingestion.file_path.name}'? This stops all future retries.",
            abort=True,
        )

    tracker.mark_as_permanent(file_path)

    click.echo(f"✓ Marked as permanently abandoned: {ingestion.file_path.name}")
    click.echo("  Use 'ingest failed retry' to undo this if needed.")


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
    click.echo(f"Broken links: {stats.get('broken_links', 0)}")
    click.echo(f"Orphan pages: {stats.get('orphan_pages', 0)}")

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

    if not 0.0 <= min_score <= 1.0:
        click.echo("Error: --min-score must be between 0.0 and 1.0", err=True)
        raise click.Abort()

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

    click.echo(f"\n✓ Metadata index: {stats.get('metadata_count', 0)} pages")
    click.echo(f"✓ Fulltext index: {stats.get('fulltext_count', 0)} documents")
    click.echo(f"✓ Backlink index: {stats.get('backlink_count', 0)} pages")
    click.echo(f"✓ Graph edge index: {stats.get('graph_edge_count', 0)} pages")


@govern.command("update-backlinks")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option("--page-id", help="Update backlinks for a specific page ID only")
@click.option("--all", "update_all", is_flag=True, help="Rebuild all backlinks from disk")
def govern_update_backlinks(wiki_base: Path, page_id: str | None, update_all: bool):
    """Update backlink index for changed pages.

    Use --page-id to re-index a single page, or --all to rebuild the full index.
    Without flags, detects and updates pages whose content has changed since last index.
    """
    from llm_wiki.index.backlinks import BacklinkIndex
    from llm_wiki.utils.frontmatter import parse_frontmatter

    index = BacklinkIndex(index_dir=wiki_base / "index")
    index.load()

    if update_all:
        click.echo("Rebuilding full backlink index from disk...")
        count = index.rebuild_from_pages(wiki_base)
        index.save()
        stats = index.get_link_stats()
        click.echo(f"\n✓ Indexed {count} pages")
        click.echo(f"  Forward links: {stats['total_forward_links']}")
        click.echo(f"  Broken links:  {stats['total_broken_links']}")
        return

    if page_id:
        # Find the page file
        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            click.echo(f"Error: Domains directory not found at {domains_dir}", err=True)
            raise click.Abort()
        page_file = None
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            candidate = domain_dir / "pages" / f"{page_id}.md"
            if candidate.exists():
                page_file = candidate
                break

        if not page_file:
            click.echo(f"Error: Page '{page_id}' not found in any domain", err=True)
            raise click.Abort()

        content = page_file.read_text(encoding="utf-8")
        _, body = parse_frontmatter(content)
        diff = index.update_page_links(page_id, body)
        index.save()

        click.echo(f"Updated backlinks for: {page_id}")
        if diff["added"]:
            click.echo(f"  Links added:   {', '.join(diff['added'])}")
        if diff["removed"]:
            click.echo(f"  Links removed: {', '.join(diff['removed'])}")
        if not diff["added"] and not diff["removed"]:
            click.echo("  No changes detected.")
        return

    # No flags: scan all pages and update stale entries
    click.echo("Scanning for pages with changed links...")
    domains_dir = wiki_base / "domains"
    if not domains_dir.exists():
        click.echo(f"Error: Domains directory not found at {domains_dir}", err=True)
        raise click.Abort()
    updated = 0
    total_added = 0
    total_removed = 0

    for domain_dir in sorted(domains_dir.iterdir()):
        if not domain_dir.is_dir():
            continue
        pages_dir = domain_dir / "pages"
        if not pages_dir.exists():
            continue
        for page_file in sorted(pages_dir.glob("*.md")):
            try:
                content = page_file.read_text(encoding="utf-8")
                metadata, body = parse_frontmatter(content)
                pid = metadata.get("id", page_file.stem)
                diff = index.update_page_links(pid, body)
                if diff["added"] or diff["removed"]:
                    updated += 1
                    total_added += len(diff["added"])
                    total_removed += len(diff["removed"])
            except Exception as e:
                click.echo(f"  Warning: could not process {page_file.name}: {e}", err=True)

    index.save()
    click.echo(f"\n✓ Pages with changes: {updated}")
    click.echo(f"  Links added:   {total_added}")
    click.echo(f"  Links removed: {total_removed}")


@govern.command("routing-mistakes")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option(
    "--min-confidence",
    type=float,
    default=0.3,
    help="Minimum confidence threshold (0.0-1.0)",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    help="Output file for report (defaults to wiki_system/reports/)",
)
def govern_routing_mistakes(wiki_base: Path, min_confidence: float, output: Path | None):
    """Detect pages that may be routed to the wrong domain."""
    from llm_wiki.governance.routing_mistakes import RoutingMistakeDetector

    if not 0.0 <= min_confidence <= 1.0:
        click.echo("Error: --min-confidence must be between 0.0 and 1.0", err=True)
        raise click.Abort()

    click.echo("Detecting routing mistakes in wiki...")

    try:
        detector = RoutingMistakeDetector(min_confidence=min_confidence, wiki_base=wiki_base)
        report = detector.analyze_all_pages(wiki_base)

        click.echo(f"\n✓ Scanned {report.total_pages_scanned} pages")
        click.echo(f"✓ Detected {report.total_mistakes} potential routing mistakes")
        click.echo(f"  - High confidence: {len(report.high_confidence)}")
        click.echo(f"  - Medium confidence: {len(report.medium_confidence)}")
        click.echo(f"  - Low confidence: {len(report.low_confidence)}")

        # Generate report
        if output:
            report_path = output
        else:
            from datetime import UTC, datetime

            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            report_path = wiki_base / "reports" / f"routing_mistakes_{timestamp}.md"

        detector.generate_report(report, report_path)
        click.echo(f"\n✓ Report saved: {report_path}")

        # Print high confidence mistakes inline
        if report.high_confidence:
            click.echo("\nHigh Confidence Routing Mistakes:")
            for mistake in report.high_confidence[:10]:
                click.echo(f"\n  {mistake.page_id}")
                click.echo(
                    f"    Current: {mistake.current_domain} -> Suggested: {mistake.suggested_domain}"
                )
                click.echo(f"    Confidence: {mistake.confidence:.2f}")
                click.echo(f"    Reasons: {'; '.join(mistake.reasons[:2])}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort() from e


@main.group()
def claims():
    """Extract and query factual claims from wiki pages."""
    pass


@claims.command("extract")
@click.argument("page_id")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option(
    "--domain",
    default=None,
    help="Domain containing the page (searches all domains if omitted)",
)
@click.option(
    "--min-confidence",
    type=float,
    default=0.5,
    help="Minimum confidence threshold for displayed claims (0.0-1.0)",
)
def claims_extract(page_id: str, wiki_base: Path, domain: str | None, min_confidence: float):
    """Extract factual claims from a wiki page."""

    from llm_wiki.extraction.claims import ClaimsExtractor
    from llm_wiki.models.client import create_model_client
    from llm_wiki.models.config import ModelProviderConfig
    from llm_wiki.utils.frontmatter import parse_frontmatter

    # Find the page file
    wiki_base = Path(wiki_base)
    page_file = None

    if domain:
        # Look in specific domain
        for subdir in ("pages", "queue"):
            candidate = wiki_base / "domains" / domain / subdir / f"{page_id}.md"
            if candidate.exists():
                page_file = candidate
                break
    else:
        # Search all domains
        for domain_dir in (wiki_base / "domains").iterdir():
            if not domain_dir.is_dir():
                continue
            for subdir in ("pages", "queue"):
                candidate = domain_dir / subdir / f"{page_id}.md"
                if candidate.exists():
                    page_file = candidate
                    break
            if page_file:
                break

    if not page_file:
        click.echo(f"Error: page '{page_id}' not found", err=True)
        raise click.Abort()

    content_text = page_file.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(content_text)

    try:
        config = ModelProviderConfig(provider="ollama", model="llama3.2:3b")
        client = create_model_client(config)
        extractor = ClaimsExtractor(client=client)
        extracted = extractor.extract_claims(body, metadata, page_id=page_id)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort() from e

    filtered = [c for c in extracted if c.confidence >= min_confidence]
    click.echo(f"\nClaims for '{page_id}' (min confidence {min_confidence}):")
    click.echo("=" * 60)

    if not filtered:
        click.echo("No claims found above confidence threshold.")
        return

    for i, claim in enumerate(filtered, 1):
        click.echo(f"\n{i}. {claim.claim}")
        click.echo(f"   Confidence: {claim.confidence:.2f}")
        click.echo(f"   Source: {claim.source_reference}")
        if claim.temporal_context:
            click.echo(f"   When: {claim.temporal_context}")
        if claim.qualifiers:
            click.echo(f"   Qualifiers: {', '.join(claim.qualifiers)}")

    click.echo(f"\nTotal: {len(filtered)} claims")


@claims.command("search")
@click.argument("query_text")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
@click.option(
    "--min-confidence",
    type=float,
    default=0.0,
    help="Minimum confidence threshold (0.0-1.0)",
)
@click.option("--limit", default=20, help="Maximum results to return")
def claims_search(query_text: str, wiki_base: Path, min_confidence: float, limit: int):
    """Search claims across all wiki pages."""
    from llm_wiki.index.metadata import MetadataIndex

    index = MetadataIndex(index_dir=Path(wiki_base) / "index")
    index.load()

    results = index.search_claims(query_text, min_confidence=min_confidence)

    click.echo(f"\nClaims matching '{query_text}':")
    click.echo("=" * 60)

    if not results:
        click.echo("No matching claims found.")
        return

    for i, claim in enumerate(results[:limit], 1):
        click.echo(f"\n{i}. {claim['text']}")
        click.echo(f"   Page: {claim['page_id']}")
        click.echo(f"   Confidence: {claim.get('confidence', 0.0):.2f}")
        click.echo(f"   Source: {claim.get('source_ref', 'unknown')}")
        if claim.get("temporal_context"):
            click.echo(f"   When: {claim['temporal_context']}")

    click.echo(f"\nTotal: {len(results)} matches (showing {min(len(results), limit)})")


@claims.command("list")
@click.argument("page_id")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def claims_list(page_id: str, wiki_base: Path):
    """List all indexed claims for a wiki page."""
    from llm_wiki.index.metadata import MetadataIndex

    index = MetadataIndex(index_dir=Path(wiki_base) / "index")
    index.load()

    page_claims = index.get_claims_for_page(page_id)

    click.echo(f"\nIndexed claims for '{page_id}':")
    click.echo("=" * 60)

    if not page_claims:
        click.echo("No indexed claims found. Run 'govern rebuild-index' to rebuild.")
        return

    for i, claim in enumerate(page_claims, 1):
        click.echo(f"\n{i}. {claim['text']}")
        click.echo(f"   Confidence: {claim.get('confidence', 0.0):.2f}")
        click.echo(f"   Source: {claim.get('source_ref', 'unknown')}")

    click.echo(f"\nTotal: {len(page_claims)} claims")


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
    "--since",
    type=str,
    default=None,
    help="Only include pages updated at or after this date (ISO format: YYYY-MM-DD)",
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
    since: str | None,
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
            domain,
            output_file=output,
            min_quality=min_quality,
            max_pages=max_pages,
            since_date=since,
        )
    else:
        click.echo("Exporting all domains...")
        result = exporter.export_all(
            output_file=output,
            min_quality=min_quality,
            max_pages=max_pages,
            since_date=since,
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


@main.group()
def graph():
    """Query the graph edge index."""
    pass


@graph.command("edges")
@click.argument("node")
@click.option("--direction", type=click.Choice(["from", "to", "both"]), default="both")
@click.option("--type", "edge_type", default=None, help="Filter by edge type")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def graph_edges(node: str, direction: str, edge_type: str | None, wiki_base: Path):
    """Show edges from/to a node in the graph."""
    from llm_wiki.index.graph_edges import GraphEdgeIndex

    index = GraphEdgeIndex(index_dir=Path(wiki_base) / "index")
    index.load()

    out = index.find_outgoing(node, edge_type) if direction in ("from", "both") else []
    inc = index.find_incoming(node, edge_type) if direction in ("to", "both") else []

    if not out and not inc:
        click.echo(f"No edges found for node '{node}'.")
        click.echo("Run 'llm-wiki govern rebuild-index' to refresh.")
        return

    click.echo(f"Graph edges for: {node}\n")
    if out:
        click.echo(f"Outgoing ({len(out)}):")
        for e in out:
            click.echo(f"  -> [{e['type']}] {e['target']}  (weight: {e['weight']:.2f})")
    if inc:
        click.echo(f"\nIncoming ({len(inc)}):")
        for e in inc:
            click.echo(f"  <- [{e['type']}] {e['source']}  (weight: {e['weight']:.2f})")


@graph.command("path")
@click.argument("source")
@click.argument("target")
@click.option("--max-depth", default=3, help="Maximum path length (edges)")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def graph_path(source: str, target: str, max_depth: int, wiki_base: Path):
    """Find directed paths between two nodes."""
    from llm_wiki.index.graph_edges import GraphEdgeIndex

    index = GraphEdgeIndex(index_dir=Path(wiki_base) / "index")
    index.load()

    paths = index.find_path(source, target, max_depth=max_depth)

    if not paths:
        click.echo(f"No path found from '{source}' to '{target}' within {max_depth} hops.")
        return

    click.echo(f"Paths from '{source}' to '{target}' ({len(paths)} found):\n")
    for i, path in enumerate(paths, 1):
        if not path:
            click.echo(f"  {i}. (same node)")
            continue
        parts = [path[0]["source"]]
        for edge in path:
            parts.append(f"--[{edge['type']}]-->")
            parts.append(edge["target"])
        click.echo(f"  {i}. {' '.join(parts)}")


@graph.command("neighbors")
@click.argument("node")
@click.option("--depth", default=1, help="Number of hops")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def graph_neighbors(node: str, depth: int, wiki_base: Path):
    """Find all nodes reachable within N hops."""
    from llm_wiki.index.graph_edges import GraphEdgeIndex

    index = GraphEdgeIndex(index_dir=Path(wiki_base) / "index")
    index.load()

    neighbours = index.find_neighbors(node, depth=depth)

    if not neighbours:
        click.echo(f"No neighbours found for '{node}' within {depth} hop(s).")
        return

    click.echo(f"Neighbours of '{node}' within {depth} hop(s): {len(neighbours)}\n")
    for n in sorted(neighbours):
        click.echo(f"  {n}")


@graph.command("subgraph")
@click.argument("nodes", nargs=-1, required=True)
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def graph_subgraph(nodes: tuple[str, ...], wiki_base: Path):
    """Extract the subgraph containing the given nodes."""
    from llm_wiki.index.graph_edges import GraphEdgeIndex

    index = GraphEdgeIndex(index_dir=Path(wiki_base) / "index")
    index.load()

    sub = index.get_subgraph(set(nodes))
    click.echo(f"Subgraph: {len(sub['nodes'])} nodes, {len(sub['edges'])} edges\n")
    for e in sub["edges"]:
        click.echo(f"  {e['source']} --[{e['type']}]--> {e['target']}  (weight: {e['weight']:.2f})")


@graph.command("stats")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def graph_stats(wiki_base: Path):
    """Show graph edge index statistics."""
    from llm_wiki.index.graph_edges import GraphEdgeIndex

    index = GraphEdgeIndex(index_dir=Path(wiki_base) / "index")
    index.load()

    stats = index.get_stats()
    click.echo("Graph edge index statistics:")
    click.echo(f"  Total edges: {stats['total_edges']}")
    click.echo(f"  Total nodes: {stats['total_nodes']}")
    if stats["edges_by_type"]:
        click.echo("\n  Edges by type:")
        for etype, cnt in sorted(stats["edges_by_type"].items()):
            click.echo(f"    {etype}: {cnt}")


# ---------------------------------------------------------------------------
# changes commands
# ---------------------------------------------------------------------------


@main.group()
def changes():
    """View and query the wiki change log."""
    pass


@changes.command("list")
@click.option("--page", help="Filter to a specific page ID")
@click.option("--since", help="Only show changes since this date (ISO format, e.g. 2024-01-01)")
@click.option("--limit", default=20, show_default=True, help="Maximum entries to show")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def changes_list(page: str | None, since: str | None, limit: int, wiki_base: Path):
    """List recent changes across all pages (or for a specific page)."""
    from llm_wiki.changelog.log import ChangeLog

    cl = ChangeLog(changelog_dir=Path(wiki_base) / "changelog")
    cl.load_index()

    if page:
        entries = cl.get_page_history(page, limit=limit)
    else:
        since_dt = None
        if since:
            from datetime import datetime

            try:
                since_dt = datetime.fromisoformat(since).replace(tzinfo=UTC)
            except ValueError:
                click.echo(f"Error: invalid date format {since!r}. Use ISO format.", err=True)
                raise click.Abort() from None
        entries = cl.get_recent_changes(since=since_dt, limit=limit)

    if not entries:
        click.echo("No changes found.")
        return

    click.echo(f"{'Change ID':<18} {'Timestamp':<22} {'Type':<12} {'Actor':<20} Page")
    click.echo("-" * 90)
    for e in entries:
        ts = e.timestamp[:19].replace("T", " ")
        click.echo(f"{e.id:<18} {ts:<22} {e.change_type:<12} {e.actor:<20} {e.page_id}")


@changes.command("show")
@click.argument("change_id")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def changes_show(change_id: str, wiki_base: Path):
    """Show full details of a single change entry."""
    from llm_wiki.changelog.log import ChangeLog

    cl = ChangeLog(changelog_dir=Path(wiki_base) / "changelog")
    cl.load_index()

    entry = cl.get_entry(change_id)
    if not entry:
        click.echo(f"Error: change {change_id!r} not found.", err=True)
        raise click.Abort()

    click.echo(cl.format_diff(entry))


@changes.command("diff")
@click.argument("page_id")
@click.option("--from", "from_date", help="Start date (ISO format)")
@click.option("--to", "to_date", help="End date (ISO format)")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def changes_diff(page_id: str, from_date: str | None, to_date: str | None, wiki_base: Path):
    """Show a diff of all changes to a page in a time window."""
    from datetime import datetime

    from llm_wiki.changelog.log import ChangeLog

    cl = ChangeLog(changelog_dir=Path(wiki_base) / "changelog")

    from_dt = None
    to_dt = None
    try:
        if from_date:
            from_dt = datetime.fromisoformat(from_date).replace(tzinfo=UTC)
        if to_date:
            to_dt = datetime.fromisoformat(to_date).replace(tzinfo=UTC)
    except ValueError as e:
        click.echo(f"Error: invalid date format: {e}", err=True)
        raise click.Abort() from e

    click.echo(cl.format_page_diff(page_id, from_dt=from_dt, to_dt=to_dt))


@changes.command("stats")
@click.option(
    "--wiki-base",
    type=click.Path(file_okay=False, path_type=Path),
    default="wiki_system",
    help="Path to wiki base directory",
)
def changes_stats(wiki_base: Path):
    """Show change log statistics."""
    from llm_wiki.changelog.log import ChangeLog

    cl = ChangeLog(changelog_dir=Path(wiki_base) / "changelog")
    cl.load_index()

    stats = cl.get_change_stats()
    click.echo(f"Total changes: {stats['total_changes']}")
    click.echo(f"Total pages:   {stats['total_pages']}")

    if stats["changes_by_type"]:
        click.echo("\nChanges by type:")
        for ct, cnt in sorted(stats["changes_by_type"].items()):
            click.echo(f"  {ct}: {cnt}")

    if stats["changes_by_actor"]:
        click.echo("\nChanges by actor:")
        for actor, cnt in sorted(stats["changes_by_actor"].items(), key=lambda x: -x[1]):
            click.echo(f"  {actor}: {cnt}")

    if stats["most_changed"]:
        click.echo("\nMost changed pages:")
        for item in stats["most_changed"]:
            click.echo(f"  {item['page_id']}: {item['count']} changes")


if __name__ == "__main__":
    main()
