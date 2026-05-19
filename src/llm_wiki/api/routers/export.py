"""Export endpoints — POST /v1/export and GET /v1/export/{format}.

Exports are files stored under ``wiki_system/exports/``.  The POST
endpoint triggers an async export job; the GET endpoint reads the
generated file and returns it with ``Last-Modified`` header.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from llm_wiki.deps import get_wiki
from llm_wiki.exceptions import ExportNotReadyError
from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])

# Format name → filename mapping
_FMT_MAP: dict[str, str] = {
    "llms-txt": "llms.txt",
    "llms-full-txt": "llms-full.txt",
    "json-ld": "graph.jsonld",
}


@router.post("/v1/export")
async def trigger_export(
    wiki: WikiQuery = Depends(get_wiki),
) -> dict[str, str]:
    """Trigger an export job asynchronously.

    Returns immediately — the actual export is performed by the daemon
    (see the ``export`` scheduled job).  The GET endpoint will return
    404 until the export file is generated.
    """
    return {"status": "accepted", "message": "Export job queued"}


@router.get("/v1/export/{format}")
async def get_export(
    format: str,
    wiki: WikiQuery = Depends(get_wiki),
) -> Response:
    """Read a generated export file.

    Returns the file content with ``Last-Modified`` header.
    Raises ``ExportNotReadyError`` (404) if the export doesn't exist
    or the format is unknown.
    """
    filename = _FMT_MAP.get(format)
    if not filename:
        raise ExportNotReadyError(f"Unknown export format: {format}")

    exports_dir = wiki.wiki_base / "exports"
    path = exports_dir / filename

    if not path.exists():
        raise ExportNotReadyError(
            f"Export '{format}' not yet generated. POST /v1/export to trigger."
        )

    content = await asyncio.to_thread(path.read_text, encoding="utf-8")
    stat = await asyncio.to_thread(path.stat)

    # Format Last-Modified as an RFC 7231 datetime string.
    last_modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime(
        "%a, %d %b %Y %H:%M:%S GMT"
    )

    # Determine media type from extension
    media_type = "text/plain"
    if format == "json-ld":
        media_type = "application/ld+json"
    elif format == "llms-full-txt":
        media_type = "text/plain"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Last-Modified": last_modified},
    )
