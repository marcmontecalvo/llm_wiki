"""Unit tests for the archive service and CLI commands (Story 3-6)."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from llm_wiki.api.services.archive import (
    archive_page,
    archive_stale_pages,
    find_page_by_id,
    unarchive_page,
)
from llm_wiki.query.search import WikiQuery


def _make_wiki_page(
    wiki_base: Path,
    domain: str,
    page_id: str,
    title: str,
    body: str = "test content",
    updated_at_days_ago: int | None = None,
) -> Path:
    """Create a minimal wiki structure with a page file."""
    domains_dir = wiki_base / "domains" / domain
    pages_dir = domains_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    frontmatter = f"---\nid: {page_id}\ntitle: {title}\ndomain: {domain}\nkind: concept\n"
    if updated_at_days_ago is not None:
        from datetime import datetime, timedelta  # noqa: PLC0415

        ts = (datetime.now(UTC) - timedelta(days=updated_at_days_ago)).isoformat()
        frontmatter += f"updated: {ts}\n"

    page_file = pages_dir / f"{page_id}.md"
    page_file.write_text(f"{frontmatter}---\n{body}\n")
    return page_file


# ---------------------------------------------------------------------------
# find_page_by_id
# ---------------------------------------------------------------------------


class TestFindPageById:
    def test_finds_active_page(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "page-a", "A")
        result = find_page_by_id("page-a", tmp_path)
        assert result is not None
        assert result["page_id"] == "page-a"
        assert result["domain"] == "ml"
        assert result["archived"] is False

    def test_finds_archived_page(self, tmp_path: Path):
        page_file = _make_wiki_page(tmp_path, "ml", "page-a", "A")
        # Move to archive
        archive_dir = tmp_path / "domains" / "ml" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_dir.joinpath("page-a.md").write_text(page_file.read_text())
        page_file.unlink()

        result = find_page_by_id("page-a", tmp_path)
        assert result is not None
        assert result["archived"] is True

    def test_returns_none_for_missing(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "page-a", "A")
        result = find_page_by_id("nonexistent", tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# archive_page
# ---------------------------------------------------------------------------


class TestArchivePage:
    def test_archives_page(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "page-a", "A", updated_at_days_ago=0)
        result = archive_page("page-a", tmp_path)
        assert result["status"] == "success"
        assert (tmp_path / "domains" / "ml" / "archive" / "page-a.md").exists()
        assert not (tmp_path / "domains" / "ml" / "pages" / "page-a.md").exists()

        # Verify frontmatter updated
        content = (tmp_path / "domains" / "ml" / "archive" / "page-a.md").read_text()
        assert "archived_at:" in content

    def test_idempotent_archive(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "page-a", "A", updated_at_days_ago=0)
        archive_page("page-a", tmp_path)
        result = archive_page("page-a", tmp_path)
        assert result["status"] == "success"
        assert "already archived" in result["message"]
        # Only one file in archive
        assert len(list((tmp_path / "domains" / "ml" / "archive").glob("*.md"))) == 1

    def test_not_found(self, tmp_path: Path):
        result = archive_page("nope", tmp_path)
        assert result["status"] == "error"
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# unarchive_page
# ---------------------------------------------------------------------------


class TestUnarchivePage:
    def test_restores_page(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "page-a", "A", updated_at_days_ago=0)
        archive_page("page-a", tmp_path)
        result = unarchive_page("page-a", tmp_path)
        assert result["status"] == "success"
        assert (tmp_path / "domains" / "ml" / "pages" / "page-a.md").exists()
        assert not (tmp_path / "domains" / "ml" / "archive" / "page-a.md").exists()

    def test_error_not_archived(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "page-a", "A", updated_at_days_ago=0)
        result = unarchive_page("page-a", tmp_path)
        assert result["status"] == "error"
        assert "not archived" in result["error"]

    def test_error_page_not_found(self, tmp_path: Path):
        result = unarchive_page("nope", tmp_path)
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# archive_stale_pages
# ---------------------------------------------------------------------------


class TestArchiveStalePages:
    def test_archives_stale_pages(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "old-page", "Old", updated_at_days_ago=100)
        _make_wiki_page(tmp_path, "ml", "new-page", "New", updated_at_days_ago=5)

        result = archive_stale_pages(tmp_path)
        assert result["status"] == "success"
        assert result["archived"] == 1
        assert not (tmp_path / "domains" / "ml" / "pages" / "old-page.md").exists()
        assert (tmp_path / "domains" / "ml" / "pages" / "new-page.md").exists()

    def test_dry_run_no_moves(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "old-page", "Old", updated_at_days_ago=100)

        result = archive_stale_pages(tmp_path, dry_run=True)
        assert result["status"] == "success"
        assert result["archived"] == 0
        assert result["skipped"] == 1
        assert (tmp_path / "domains" / "ml" / "pages" / "old-page.md").exists()


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


class TestCLIArchive:
    def test_cli_archive_human(self, tmp_path: Path):
        from click.testing import CliRunner

        from llm_wiki.cli import main

        _make_wiki_page(tmp_path, "ml", "page-a", "A", updated_at_days_ago=0)
        runner = CliRunner()
        result = runner.invoke(main, ["govern", "archive", "page-a", "--wiki-base", str(tmp_path)])
        assert result.exit_code == 0
        assert "OK:" in result.output

    def test_cli_archive_already(self, tmp_path: Path):
        from click.testing import CliRunner

        from llm_wiki.cli import main

        _make_wiki_page(tmp_path, "ml", "page-a", "A", updated_at_days_ago=0)
        runner = CliRunner()
        runner.invoke(main, ["govern", "archive", "page-a", "--wiki-base", str(tmp_path)])
        result = runner.invoke(main, ["govern", "archive", "page-a", "--wiki-base", str(tmp_path)])
        assert result.exit_code == 0
        assert "already archived" in result.output

    def test_cli_archive_not_found(self, tmp_path: Path):
        from click.testing import CliRunner

        from llm_wiki.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["govern", "archive", "nope", "--wiki-base", str(tmp_path)])
        assert result.exit_code != 0

    def test_cli_unarchive(self, tmp_path: Path):
        from click.testing import CliRunner

        from llm_wiki.cli import main

        _make_wiki_page(tmp_path, "ml", "page-a", "A", updated_at_days_ago=0)
        runner = CliRunner()
        runner.invoke(main, ["govern", "archive", "page-a", "--wiki-base", str(tmp_path)])
        result = runner.invoke(
            main, ["govern", "unarchive", "page-a", "--wiki-base", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "OK:" in result.output

    def test_cli_unarchive_not_archived(self, tmp_path: Path):
        from click.testing import CliRunner

        from llm_wiki.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["govern", "unarchive", "nope", "--wiki-base", str(tmp_path)])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# get_page fallback to archive
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# WikiQuery.search() exclude_archived
# ---------------------------------------------------------------------------


class TestSearchExcludesArchived:
    def test_default_excludes_archived(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "fresh-page", "Fresh", updated_at_days_ago=5)
        _make_wiki_page(tmp_path, "ml", "deprecated-guide", "Deprecated", updated_at_days_ago=100)

        # Archive the stale page manually
        archive_page("deprecated-guide", tmp_path)

        wiki = WikiQuery(wiki_base=tmp_path)
        wiki.rebuild_indexes()
        results = wiki.search(query="", limit=50)
        page_ids = [r.get("page_id") for r in results]
        assert "fresh-page" in page_ids
        assert "deprecated-guide" not in page_ids

    def test_include_archived_includes_stale(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "fresh-page", "Fresh", updated_at_days_ago=5)
        _make_wiki_page(tmp_path, "ml", "deprecated-guide", "Deprecated", updated_at_days_ago=100)

        archive_page("deprecated-guide", tmp_path)

        wiki = WikiQuery(wiki_base=tmp_path)
        wiki.rebuild_indexes()
        results = wiki.search(query="", include_archived=True, limit=50)
        page_ids = [r.get("page_id") for r in results]
        assert "fresh-page" in page_ids
        assert "deprecated-guide" in page_ids

        # Verify archived flag is set
        archived = [r for r in results if r.get("page_id") == "deprecated-guide"]
        assert len(archived) == 1
        assert archived[0]["archived"] is True


class TestListPagesExcludesArchived:
    def test_default_excludes_archived(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "fresh-page", "Fresh", updated_at_days_ago=5)
        _make_wiki_page(tmp_path, "ml", "old-page", "Old", updated_at_days_ago=100)

        archive_page("old-page", tmp_path)

        wiki = WikiQuery(wiki_base=tmp_path)
        wiki.rebuild_indexes()
        items, _ = wiki.list_pages(domain="ml", include_archived=False)
        page_ids = [p.get("page_id") or p.get("id") for p in items]
        assert "fresh-page" in page_ids
        assert "old-page" not in page_ids

    def test_include_archived_includes_stale(self, tmp_path: Path):
        _make_wiki_page(tmp_path, "ml", "fresh-page", "Fresh", updated_at_days_ago=5)
        _make_wiki_page(tmp_path, "ml", "old-page", "Old", updated_at_days_ago=100)

        archive_page("old-page", tmp_path)

        wiki = WikiQuery(wiki_base=tmp_path)
        wiki.rebuild_indexes()
        items, _ = wiki.list_pages(domain="ml", include_archived=True)
        page_ids = [p.get("page_id") or p.get("id") for p in items]
        assert "fresh-page" in page_ids
        assert "old-page" in page_ids


# ---------------------------------------------------------------------------
# GovernanceJob archive integration
# ---------------------------------------------------------------------------


class TestGovernanceArchiveIntegration:
    def test_archive_stale_in_governance_job(self, tmp_path: Path):
        from llm_wiki.daemon.jobs.governance import GovernanceJob

        _make_wiki_page(tmp_path, "ml", "ancient-page", "Ancient", updated_at_days_ago=100)
        _make_wiki_page(tmp_path, "ml", "recent-page", "Recent", updated_at_days_ago=5)

        job = GovernanceJob(wiki_base=tmp_path)
        result = job.execute()

        assert result["status"] == "success"
        assert result.get("archived_pages", 0) >= 1
        assert not (tmp_path / "domains" / "ml" / "pages" / "ancient-page.md").exists()
        assert (tmp_path / "domains" / "ml" / "pages" / "recent-page.md").exists()

    def test_governance_no_archived_pages_when_none_stale(self, tmp_path: Path):
        from llm_wiki.daemon.jobs.governance import GovernanceJob

        _make_wiki_page(tmp_path, "ml", "fresh-page", "Fresh", updated_at_days_ago=1)

        job = GovernanceJob(wiki_base=tmp_path)
        result = job.execute()

        assert result["status"] == "success"
        assert result.get("archived_pages", 0) == 0

    def test_get_page_returns_archived_flag(self, tmp_path: Path):
        from llm_wiki.query.search import WikiQuery

        _make_wiki_page(tmp_path, "ml", "page-a", "A", updated_at_days_ago=0)
        archive_page("page-a", tmp_path)

        wiki = WikiQuery(wiki_base=tmp_path)
        result = wiki.get_page("page-a")
        assert result is not None
        assert result["archived"] is True
