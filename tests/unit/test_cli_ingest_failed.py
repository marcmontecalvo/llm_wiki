"""Tests for CLI ingest failed/stats commands."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from llm_wiki.cli import main
from llm_wiki.ingest.failed import FailedIngestionsTracker, FailureReason


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def wiki_base(tmp_path):
    state_dir = tmp_path / "state"
    inbox = tmp_path / "inbox"
    for subdir in [
        state_dir,
        inbox / "new",
        inbox / "processing",
        inbox / "done",
        inbox / "failed",
    ]:
        subdir.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def tracker(wiki_base):
    return FailedIngestionsTracker(state_dir=wiki_base / "state")


class TestIngestStats:
    def test_stats_empty(self, runner, wiki_base):
        result = runner.invoke(main, ["ingest", "stats", "--wiki-base", str(wiki_base)])
        assert result.exit_code == 0
        assert "Total failed:        0" in result.output

    def test_stats_with_failures(self, runner, wiki_base, tracker):
        tracker.record_failure(Path("/some/file.md"), FailureReason.LLM_TIMEOUT)
        tracker.record_failure(Path("/other/file.md"), FailureReason.INVALID_FORMAT)

        result = runner.invoke(main, ["ingest", "stats", "--wiki-base", str(wiki_base)])
        assert result.exit_code == 0
        assert "Total failed:        2" in result.output
        assert "Permanent failures:  1" in result.output
        assert "llm_timeout" in result.output
        assert "invalid_format" in result.output


class TestIngestFailedList:
    def test_list_empty(self, runner, wiki_base):
        result = runner.invoke(main, ["ingest", "failed", "list", "--wiki-base", str(wiki_base)])
        assert result.exit_code == 0
        assert "No failed ingestions" in result.output

    def test_list_with_failures(self, runner, wiki_base, tracker):
        tracker.record_failure(Path("/some/doc.md"), FailureReason.LLM_TIMEOUT)
        tracker.record_failure(Path("/other/bad.md"), FailureReason.CORRUPTED_FILE)

        result = runner.invoke(main, ["ingest", "failed", "list", "--wiki-base", str(wiki_base)])
        assert result.exit_code == 0
        assert "doc.md" in result.output
        assert "bad.md" in result.output
        assert "llm_timeout" in result.output
        assert "corrupted_file" in result.output

    def test_list_permanent_only(self, runner, wiki_base, tracker):
        tracker.record_failure(Path("/transient.md"), FailureReason.LLM_TIMEOUT)
        tracker.record_failure(Path("/permanent.md"), FailureReason.CORRUPTED_FILE)

        result = runner.invoke(
            main,
            ["ingest", "failed", "list", "--wiki-base", str(wiki_base), "--permanent-only"],
        )
        assert result.exit_code == 0
        assert "permanent.md" in result.output
        assert "transient.md" not in result.output


class TestIngestFailedRetry:
    def test_retry_success(self, runner, wiki_base, tracker):
        # Create file in failed/ dir and record failure under that path (as watcher does)
        failed_file = wiki_base / "inbox" / "failed" / "test.md"
        failed_file.write_text("content")
        tracker.record_failure(failed_file, FailureReason.LLM_TIMEOUT)

        result = runner.invoke(
            main, ["ingest", "failed", "retry", str(failed_file), "--wiki-base", str(wiki_base)]
        )
        assert result.exit_code == 0
        assert "Queued for retry" in result.output
        # File should be moved to new/
        assert (wiki_base / "inbox" / "new" / "test.md").exists()
        assert not failed_file.exists()
        # Failure record should be cleared (using failed_path as key)
        fresh_tracker = FailedIngestionsTracker(state_dir=wiki_base / "state")
        assert fresh_tracker.get_failed_ingestion(failed_file) is None

    def test_retry_clears_error_file(self, runner, wiki_base, tracker):
        failed_file = wiki_base / "inbox" / "failed" / "test.md"
        failed_file.write_text("content")
        error_file = failed_file.with_suffix(".md.error")
        error_file.write_text("some error")
        tracker.record_failure(failed_file, FailureReason.LLM_TIMEOUT)

        runner.invoke(
            main, ["ingest", "failed", "retry", str(failed_file), "--wiki-base", str(wiki_base)]
        )
        assert not error_file.exists()

    def test_retry_missing_file(self, runner, wiki_base):
        result = runner.invoke(
            main,
            ["ingest", "failed", "retry", "nonexistent.md", "--wiki-base", str(wiki_base)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "Error" in result.output


class TestIngestFailedAbandon:
    def test_abandon_with_yes_flag(self, runner, wiki_base, tracker):
        file_path = Path("/some/doc.md")
        tracker.record_failure(file_path, FailureReason.LLM_TIMEOUT)

        result = runner.invoke(
            main,
            ["ingest", "failed", "abandon", str(file_path), "--wiki-base", str(wiki_base), "--yes"],
        )
        assert result.exit_code == 0
        assert "permanently abandoned" in result.output

        # Re-load from disk to verify persisted state
        fresh_tracker = FailedIngestionsTracker(state_dir=wiki_base / "state")
        ing = fresh_tracker.get_failed_ingestion(file_path)
        assert ing is not None
        assert ing.permanent_failure is True

    def test_abandon_not_found(self, runner, wiki_base):
        result = runner.invoke(
            main,
            [
                "ingest",
                "failed",
                "abandon",
                "nonexistent.md",
                "--wiki-base",
                str(wiki_base),
                "--yes",
            ],
        )
        assert result.exit_code != 0
        assert "No failure record" in result.output or "Error" in result.output

    def test_abandon_by_filename(self, runner, wiki_base, tracker):
        file_path = Path("/deeply/nested/path/doc.md")
        tracker.record_failure(file_path, FailureReason.NETWORK_ERROR)

        result = runner.invoke(
            main,
            ["ingest", "failed", "abandon", "doc.md", "--wiki-base", str(wiki_base), "--yes"],
        )
        assert result.exit_code == 0
        assert "permanently abandoned" in result.output

    def test_abandon_filename_collision_errors(self, runner, wiki_base, tracker):
        tracker.record_failure(Path("/path/a/doc.md"), FailureReason.NETWORK_ERROR)
        tracker.record_failure(Path("/path/b/doc.md"), FailureReason.LLM_TIMEOUT)

        result = runner.invoke(
            main,
            ["ingest", "failed", "abandon", "doc.md", "--wiki-base", str(wiki_base), "--yes"],
        )
        assert result.exit_code != 0
        assert "Multiple records" in result.output
