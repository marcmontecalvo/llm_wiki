"""Tests for Honcho push daemon job."""

from pathlib import Path
from unittest.mock import MagicMock, patch


def _create_exports(tmp_path: Path) -> Path:
    """Helper: create wikiSystem/exports with llms.txt and graph.json."""
    ws = tmp_path / "wiki_system"
    exports = ws / "exports"
    exports.mkdir(parents=True)
    exports.joinpath("llms.txt").write_text("# LLM Wiki\n\nSome content\n", encoding="utf-8")
    exports.joinpath("graph.json").write_text('{"nodes": []}', encoding="utf-8")
    return ws


def test_run_honcho_push_no_export(tmp_path: Path) -> None:
    """No llms.txt -> skipped."""
    from llm_wiki.daemon.jobs.honcho_push import (  # noqa: PLC0415
        run_honcho_push_job,
    )

    ws = tmp_path / "wiki_system"
    ws.mkdir()
    (ws / "exports").mkdir()
    result = run_honcho_push_job(wiki_base=ws)
    assert result["status"] == "skipped"
    assert "No llms.txt" in result.get("reason", "")


def test_run_honcho_push_remote(tmp_path: Path) -> None:
    """Remote mode: POST to push_url."""
    from llm_wiki.daemon.jobs.honcho_push import (  # noqa: PLC0415
        run_honcho_push_job,
    )

    ws = _create_exports(tmp_path)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_client = MagicMock()
    mock_client.post.return_value = mock_resp
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client", return_value=mock_client):
        result = run_honcho_push_job(
            wiki_base=ws,
            push_url="http://test-honcho:8000",
            push_api_key="test-key",
        )
        assert result["status"] == "success"
        assert result["mode"] == "remote"
        assert result["llms_txt_size"] > 0
        assert result["graph_included"] is True
        mock_client.post.assert_called_once()


def test_run_honcho_push_local_no_sdk(tmp_path: Path) -> None:
    """Without honcho SDK installed, return skipped."""
    from llm_wiki.daemon.jobs.honcho_push import (  # noqa: PLC0415
        run_honcho_push_job,
    )

    ws = _create_exports(tmp_path)
    with patch.dict("sys.modules", {"honcho": None}):
        result = run_honcho_push_job(wiki_base=ws)
        assert result["status"] == "skipped"
        assert "honcho package not installed" in result.get("reason", "").lower()
