# Story 1.15: Governance CLI Commands

Status: ready-for-dev

## Story

As an operator,
I want CLI commands to read governance reports and trigger governance runs manually,
So that I can inspect daemon health, review what was flagged, and run governance on demand without waiting for the next scheduled job.

**Note:** The `govern` CLI group, individual governance subcommands (`check`, `contradictions`, `duplicates`, `rebuild-index`, etc.), and `GovernanceJob` are already substantially implemented. This story adds the new required surface: `govern status`, `govern run [lint|contradictions|staleness|all]`, `govern report`, and the `inbox/staging/` routing-failed area. Read `src/llm_wiki/cli.py:787-1260` and `src/llm_wiki/daemon/jobs/governance.py` before implementing.

## Acceptance Criteria

1. **Given** `llm-wiki govern status [--json]` **When** called **Then** it prints the last-run timestamp, outcome (pass/fail/warnings), and warning count for each governance job (lint, contradictions, staleness, routing) — sourced from `state/jobs.json`.

2. **Given** `llm-wiki govern run [lint|contradictions|staleness|all] [--json]` **When** called **Then** it triggers the specified governance job synchronously and prints the structured report when complete; `--all` runs all jobs in sequence.

3. **Given** `llm-wiki govern report [--domain <name>] [--json]` **When** called **Then** it prints the latest governance report from `reports/`, filtered by domain if specified.

4. **Given** `llm-wiki govern run` is called while the daemon is running the same job **When** executed **Then** it waits for the lock or fails with a clear message — it does not silently run a concurrent governance sweep.

5. **Given** any governance CLI command is run with `--json` **When** executed **Then** it emits machine-parseable JSON to stdout (NFR-I3).

6. **Given** `GET /v1/daemon/status` **When** audited **Then** it returns governance job last-run results alongside all other daemon jobs — governance is not a separate REST resource (FR18).

7. **Given** a source dropped into the inbox matches no rule in `routing.yaml` **When** the inbox scan job processes it **Then** the file is moved to `inbox/staging/` and a governance report entry is written with `status: routing-failed` and the source path (FR53).

8. **Given** `llm-wiki govern report` or `GET /v1/daemon/status` **When** routing-failed items exist in `inbox/staging/` **Then** they appear in the governance report output with their staging path, arrival time, and `status: routing-failed` (FR53).

9. **Given** a routing-failed file exists in `inbox/staging/` **When** the operator runs `llm-wiki ingest <path> --domain <name>` **Then** the file is moved from `inbox/staging/` to `inbox/new/` and processed normally (FR53).

## Tasks / Subtasks

- [ ] Add `govern status [--json]` command to `src/llm_wiki/cli.py` (AC: 1, 5)
  - [ ] Read `state/jobs.json` and display per-job last-run info
  - [ ] Output: last timestamp, outcome, warning count for lint/contradictions/staleness/routing
  - [ ] `--json` flag: emit raw dict as JSON
- [ ] Add `govern run [lint|contradictions|staleness|all] [--json]` command (AC: 2, 4, 5)
  - [ ] `lint`: run `MetadataLinter` synchronously
  - [ ] `contradictions`: run `ContradictionDetector` synchronously
  - [ ] `staleness`: run `StalenessDetector` synchronously
  - [ ] `all`: run all three in sequence
  - [ ] Use a cross-platform lock file (`state/governance.lock`) via `O_CREAT | O_EXCL` to detect concurrent daemon run (AC: 4)
  - [ ] Print structured report; `--json` emits JSON
- [ ] Add `govern report [--domain <name>] [--json]` command (AC: 3, 5)
  - [ ] Read latest report file from `reports/` directory (sort by timestamp, take newest)
  - [ ] `--domain` filter: only show items for the specified domain
  - [ ] Include routing-failed items from `inbox/staging/` in the report (AC: 8)
- [ ] Implement `inbox/staging/` routing-failed area (AC: 7, 8, 9)
  - [ ] In `InboxWatcher._process_file()` or routing logic: when no domain matched **→** move to `inbox/staging/` instead of `inbox/failed/`
  - [ ] Write a governance report entry `{status: "routing-failed", source_path: ..., arrived_at: ...}` to `reports/routing-failed.jsonl`
  - [ ] `inbox/staging/` already created by Story 1.10 init — no mkdir needed
- [ ] Wire `llm-wiki ingest <path> --domain <name>` to handle staging-area files (AC: 9)
  - [ ] If `<path>` resolves to a file in `inbox/staging/`, move it to `inbox/new/` before processing
  - [ ] The `ingest` command already exists — add staging-area detection
- [ ] Verify `GET /v1/daemon/status` includes governance results (AC: 6)
  - [ ] Read Story 1.6 implementation — verify governance job state is included in daemon status response
  - [ ] No new REST endpoints needed — governance data comes from `state/jobs.json`

## Dev Notes

### Existing Govern Commands — Read Before Implementing

`src/llm_wiki/cli.py:787-1260` has these govern subcommands already:
- `govern check` — run all governance checks, generate report
- `govern contradictions` — contradiction detection
- `govern duplicates` / `govern merge-duplicate`
- `govern rebuild-index`
- `govern update-backlinks`
- `govern routing-mistakes`
- `govern clean-broken-links`

The new `govern status`, `govern run`, and `govern report` commands should be **consistent with** the existing style but add the `--json` flag throughout.

### govern status Implementation

```python
# src/llm_wiki/cli.py — add under @govern.command("status")
@govern.command("status")
@click.option("--json", "output_json", is_flag=True)
@click.option("--wiki-base", type=click.Path(file_okay=False, path_type=Path), default="wiki_system")
def govern_status(output_json: bool, wiki_base: Path):
    """Show last-run results for each governance job."""
    import json as _json
    jobs_path = wiki_base / "state" / "jobs.json"
    if not jobs_path.exists():
        data = {}
    else:
        data = _json.loads(jobs_path.read_text())

    governance_jobs = {
        k: v for k, v in data.items()
        if k in ("lint", "contradictions", "staleness", "routing")
    }

    if output_json:
        click.echo(_json.dumps(governance_jobs, indent=2))
        return

    for job_name, info in governance_jobs.items():
        last_run = info.get("last_run", "never")
        outcome = info.get("outcome", "unknown")
        warnings = info.get("warning_count", 0)
        click.echo(f"{job_name:20} last={last_run}  outcome={outcome}  warnings={warnings}")
```

### govern run — Concurrent Lock Pattern

Use `O_CREAT | O_EXCL` (atomic exclusive create) as a cross-platform lock file in `state/governance.lock`. Works on POSIX and Windows — no `fcntl` dependency.

```python
import os
from contextlib import contextmanager

@contextmanager
def _governance_lock(wiki_base: Path):
    """Context manager that acquires a cross-platform exclusive lock via O_CREAT|O_EXCL."""
    lock_path = wiki_base / "state" / "governance.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise click.ClickException(
            "Governance sweep is already running (daemon or another CLI instance). "
            "Wait for it to complete or check daemon logs."
        )
    try:
        yield
    finally:
        os.close(fd)
        lock_path.unlink(missing_ok=True)
```

Usage in `govern run`:

```python
with _governance_lock(wiki_base):
    _run_governance_jobs(selected_jobs, wiki_base, output_json)
```

### govern report — Routing-Failed Items

```python
@govern.command("report")
@click.option("--domain", default=None)
@click.option("--json", "output_json", is_flag=True)
@click.option("--wiki-base", type=click.Path(file_okay=False, path_type=Path), default="wiki_system")
def govern_report(domain: str | None, output_json: bool, wiki_base: Path):
    """Print latest governance report."""
    import json as _json
    reports_dir = wiki_base / "reports"
    staging_dir = wiki_base / "inbox" / "staging"

    # Find latest report file
    report_files = sorted(reports_dir.glob("governance_*.json"), reverse=True)
    report_data = _json.loads(report_files[0].read_text()) if report_files else {}

    # Append routing-failed items from staging
    if staging_dir.exists():
        staging_items = []
        for f in staging_dir.iterdir():
            if f.is_file():
                staging_items.append({
                    "status": "routing-failed",
                    "source_path": str(f),
                    "arrived_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
        if staging_items:
            report_data["routing_failed"] = staging_items

    if domain:
        # Filter: keep only items for the specified domain
        report_data = {k: v for k, v in report_data.items() if _item_in_domain(v, domain)}

    if output_json:
        click.echo(_json.dumps(report_data, indent=2))
    else:
        _print_report_human(report_data)
```

### Routing-Failed Area — InboxWatcher Change

The existing `InboxWatcher._process_file()` moves failed files to `inbox/failed/`. Add routing-failure detection:

```python
# src/llm_wiki/ingest/watcher.py — in _process_file()
# BEFORE:
#   if no domain matched: raise RoutingError(...)

# AFTER:
if matched_domain is None:
    # Move to staging instead of failed
    staging_path = self.inbox_root.parent / "staging" / source_file.name
    source_file.rename(staging_path)
    # Write routing-failed report entry
    self._write_routing_failed_entry(staging_path)
    return  # Not an error — operator action required
```

The routing-failed JSONL entry format:
```python
{
    "status": "routing-failed",
    "source_path": str(staging_path),
    "source_name": staging_path.name,
    "arrived_at": datetime.utcnow().isoformat(),
}
```

Written to: `wiki_base / "reports" / "routing-failed.jsonl"` (append mode).

### ingest CLI — Staging-Area Passthrough

```python
# src/llm_wiki/cli.py — in the existing ingest command
# Add detection: if source is in inbox/staging/, move to inbox/new/ first
def _resolve_ingest_source(source: Path, wiki_base: Path) -> Path:
    staging = wiki_base / "inbox" / "staging"
    if source.parent.resolve() == staging.resolve():
        dest = wiki_base / "inbox" / "new" / source.name
        source.rename(dest)
        return dest
    return source
```

### state/jobs.json Schema

Each governance job should write its results here after running:

```json
{
  "lint": {
    "last_run": "2026-05-17T10:00:00Z",
    "outcome": "warnings",
    "warning_count": 3,
    "error_count": 0
  },
  "contradictions": {
    "last_run": "2026-05-17T10:00:05Z",
    "outcome": "pass",
    "warning_count": 0,
    "error_count": 0
  },
  "staleness": {
    "last_run": "2026-05-17T10:00:10Z",
    "outcome": "pass",
    "warning_count": 1,
    "error_count": 0
  }
}
```

The daemon's `GovernanceJob.execute()` already writes results — verify the schema matches what `govern status` expects to read.

### Project Structure — Files to Create/Modify

```
src/llm_wiki/
├── cli.py                        UPDATE — add govern status, run, report commands
├── ingest/watcher.py             UPDATE — move routing-failed to inbox/staging/
└── daemon/jobs/governance.py     VERIFY — state/jobs.json write format
```

### Testing

`tests/unit/test_governance_cli.py`:

```python
def test_govern_status_json(tmp_path):
    jobs_path = tmp_path / "state" / "jobs.json"
    jobs_path.parent.mkdir(parents=True)
    jobs_path.write_text('{"lint": {"last_run": "2026-01-01", "outcome": "pass", "warning_count": 0}}')

    runner = CliRunner()
    result = runner.invoke(main, ["govern", "status", "--json", "--wiki-base", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "lint" in data

def test_govern_report_includes_staging(tmp_path):
    staging = tmp_path / "inbox" / "staging"
    staging.mkdir(parents=True)
    (staging / "mystery.md").write_text("orphaned")

    runner = CliRunner()
    result = runner.invoke(main, ["govern", "report", "--json", "--wiki-base", str(tmp_path)])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert any(item["status"] == "routing-failed" for item in data.get("routing_failed", []))

def test_routing_failed_moves_to_staging(tmp_path, inbox_with_unrouted_file):
    """File with no routing match moves to inbox/staging/."""
    # Trigger watcher scan
    watcher = InboxWatcher(wiki_base=tmp_path, config=config_with_no_routes)
    watcher.scan()

    staging = tmp_path / "wiki_system" / "inbox" / "staging"
    assert len(list(staging.iterdir())) == 1
```

### Critical Anti-Patterns to Avoid

- **Never move routing-failed files to `inbox/failed/`** — they go to `inbox/staging/` where operators can manually assign them (FR53)
- **Never add a separate REST endpoint for governance** — governance data surfaces through `GET /v1/daemon/status` via `state/jobs.json` (FR18)
- **Never run governance from the event loop** — `govern run` is a CLI command; it runs synchronously in the CLI process, not inside the FastAPI app

### References

- Architecture: "Governance Job Architecture" — GovernanceJob, state/jobs.json
- Architecture: "Inbox Routing" — routing.yaml, inbox/staging/ area
- Architecture: Enforcement Guidelines — rule about governance REST surface
- `src/llm_wiki/cli.py:787-1260` — existing govern commands
- `src/llm_wiki/daemon/jobs/governance.py` — GovernanceJob.execute()
- FR18: Governance results in daemon status
- FR53: routing-failed → inbox/staging/

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List
