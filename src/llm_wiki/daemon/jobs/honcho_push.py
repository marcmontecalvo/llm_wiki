"""Honcho push daemon job — write wiki export bundle to Honcho.

Supports two modes:
- Local: write to Honcho session via honcho SDK (honcho package available)
- Remote: POST export bundle to a configured push URL
"""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.paths import resolve_wiki_base

logger = logging.getLogger(__name__)


def _read_export(path: Path) -> str | None:
    """Read an export file, return text or None if missing."""
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read export %s: %s", path, e)
    return None


def push_to_remote(
    push_url: str,
    llms_txt: str,
    graph_json: str | None,
    push_api_key: str | None = None,
) -> dict:
    """POST export bundle to a remote Honcho endpoint.

    Args:
        push_url: Honcho server URL (e.g. http://localhost:8000)
        llms_txt: Contents of llms.txt export
        graph_json: Contents of graph.json export (may be None)
        push_api_key: Optional API key for authentication

    Returns:
        Dict with status and detail.
    """
    import httpx

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if push_api_key:
        headers["Authorization"] = f"Bearer {push_api_key}"

    payload = {"llms_txt": llms_txt}
    if graph_json is not None:
        payload["graph_json"] = graph_json

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{push_url}/v1/honcho/wiki-bundle", json=payload, headers=headers)
            return {
                "status": "success" if resp.status_code < 400 else "error",
                "http_status": resp.status_code,
            }
    except Exception as e:
        logger.error("Push to remote failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


def run_honcho_push_job(
    wiki_base: Path | None = None,
    honcho_base_url: str | None = None,
    honcho_workspace_id: str = "default",
    push_url: str | None = None,
    push_api_key: str | None = None,
) -> dict[str, Any]:
    """Run honcho push job.

    Writes the wiki export bundle (llms.txt + graph) to Honcho so that
    the next Honcho dream pass picks up new/changed wiki knowledge.

    Args:
        wiki_base: Base wiki directory
        push_url: Remote URL to push to (alternative to local honcho SDK)
        honcho_workspace_id: Workspace to use for local honcho
        push_api_key: API key for remote push

    Returns:
        Dict with status and file details.
    """
    wiki_base = resolve_wiki_base(wiki_base)
    exports_dir = wiki_base / "exports"
    llms_path = exports_dir / "llms.txt"
    graph_path = exports_dir / "graph.json"

    llms_txt = _read_export(llms_path)
    graph_json = _read_export(graph_path)

    if not llms_txt:
        return {"status": "skipped", "reason": "No llms.txt export found"}

    if push_url:
        logger.info("Pushing wiki export bundle to remote Honcho at %s", push_url)
        result = push_to_remote(push_url, llms_txt, graph_json, push_api_key)
        return {
            "mode": "remote",
            "push_url": push_url,
            "llms_txt_size": len(llms_txt),
            "graph_included": graph_json is not None,
            **result,
        }

    # Local mode: use honcho SDK if available
    try:
        from honcho import Honcho  # noqa: PLC0415
    except ImportError:
        return {"status": "skipped", "reason": "honcho package not installed"}

    try:
        honcho = Honcho(workspace_id=honcho_workspace_id, base_url=honcho_base_url)
        session = honcho.session("llm-wiki-bundle")
        session.add_peers("llm-wiki")

        # Upload llms.txt as a session file (parses into messages)
        from io import BytesIO  # noqa: PLC0415

        messages = session.upload_file(
            file=("llms.txt", BytesIO(llms_txt.encode()).read(), "text/plain"),
            peer="llm-wiki",
        )
        logger.info("Uploaded llms.txt to Honcho (%d messages)", len(messages))

        return {
            "mode": "local",
            "workspace": honcho_workspace_id,
            "messages_created": len(messages),
            "llms_txt_size": len(llms_txt),
            "graph_included": graph_json is not None,
            "status": "success",
        }
    except ImportError:
        return {"status": "skipped", "reason": "honcho package not installed"}
    except Exception as e:
        logger.error("Honcho push failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
