"""Tests for Honcho harvester module."""

from pathlib import Path

from llm_wiki.honcho.harvester import _build_frontmatter, harvest_conclusions


def test_build_frontmatter():
    """Frontmatter matches wiki page format."""
    conclusion = {
        "observer_id": "alice",
        "observed_id": "bob",
        "content": "Test conclusion",
    }
    fm = _build_frontmatter(conclusion)
    assert "kind: conclusion" in fm
    assert "id: honcho-alice" in fm
    assert "alice" in fm
    assert "bob" in fm


def test_harvest_conclusions_no_sessions(tmp_path: Path):
    """When honcho has no sessions, harvested=0."""
    honcho_mock = __import__("unittest").mock.MagicMock()
    honcho_mock.sessions.return_value = []

    honcho_mock._ensure_workspace = __import__("unittest").mock.MagicMock()

    result = harvest_conclusions(
        honcho=honcho_mock,
        workspace_id="test",
        wiki_base=tmp_path,
        limit_per_session=5,
    )
    assert result["status"] == "success"
    assert result["harvested"] == 0
    assert result.get("reason") == "No sessions found"


def test_harvest_conclusions_inbox_created(tmp_path: Path):
    """Harvest creates inbox/new/ even when no sessions."""
    honcho_mock = __import__("unittest").mock.MagicMock()
    honcho_mock.sessions.return_value = []

    honcho_mock._ensure_workspace = __import__("unittest").mock.MagicMock()

    harvest_conclusions(
        honcho=honcho_mock,
        workspace_id="test",
        wiki_base=tmp_path,
        limit_per_session=5,
    )

    inbox_dir = tmp_path / "inbox" / "new"
    assert inbox_dir.exists()


def test_run_harvest_job_no_sdk():
    """Harvest returns skipped when honcho package is missing."""
    import builtins

    real_import = builtins.__import__

    def prevent_import(name, *args, **kwargs):
        if name == "honcho" or name.startswith("honcho."):
            raise ImportError("honcho not installed")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = prevent_import
    try:
        from llm_wiki.honcho.harvester import run_harvest_job  # noqa: PLC0415

        result = run_harvest_job()
        assert result["status"] == "skipped"
        assert "honcho package not installed" in result.get("reason", "").lower()
    finally:
        builtins.__import__ = real_import
