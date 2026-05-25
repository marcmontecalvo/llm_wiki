"""Honcho harvest — pull session conclusions into the wiki inbox.

Converts each Honcho conclusion into a wiki markdown file with proper
frontmatter, writes it to the inbox/new/ directory, and returns a
summary of what was harvested.
"""

import logging
from pathlib import Path
from typing import Any

from llm_wiki.paths import resolve_wiki_base

logger = logging.getLogger(__name__)


def _build_frontmatter(conclusion: dict) -> str:
    """Build YAML frontmatter for a wiki page from a Honcho conclusion."""
    lines = [
        "---",
        "kind: conclusion",
        f"id: honcho-{conclusion['observer_id'][:8]}",
        f'title: "Conclusion from {conclusion["observer_id"]} about {conclusion["observed_id"]}"',
        "---",
    ]
    return "\n".join(lines) + "\n"


def harvest_conclusions(
    honcho,
    workspace_id: str,
    wiki_base: Path | None = None,
    limit_per_session: int = 10,
) -> dict[str, Any]:
    """Harvest conclusions from Honcho into the wiki inbox.

    For each active workspace session, fetches conclusions and writes
    them as wiki markdown with frontmatter to inbox/new/.

    Args:
        honcho: Honcho client instance
        workspace_id: Honcho workspace to harvest from
        wiki_base: Target wiki directory
        limit_per_session: Max conclusions to write per session

    Returns:
        Dict with harvested count and error info.
    """
    wiki_base = resolve_wiki_base(wiki_base)
    inbox_dir = wiki_base / "inbox" / "new"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    try:
        sessions = honcho.sessions(page=1, size=100)
    except Exception as e:
        logger.error("Failed to list Honcho sessions: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}

    harvested = 0
    all_sessions = list(sessions)
    if not all_sessions:
        return {"status": "success", "harvested": 0, "reason": "No sessions found"}

    for session in all_sessions:
        try:
            _ = honcho.session(session.id)
            # Use peer.conclusions.list() for self-conclusions
            peer = honcho.peer("hub")
            scope = peer.conclusions
            for page in scope.list(page=1, size=limit_per_session):
                pass
                try:
                    conclusions = [
                        {
                            "observer_id": c.observer_id,
                            "observed_id": c.observed_id,
                            "content": c.content,
                            "session_id": c.session_id,
                        }
                        for c in page
                    ]
                except (AttributeError, TypeError):
                    conclusions = []

                for c in conclusions[:limit_per_session]:
                    page_id = f"honcho-{c['observer_id'][:8]}"
                    path = inbox_dir / f"{page_id}.md"
                    if path.exists():
                        suffix = harvested + 1
                        path = inbox_dir / f"{page_id}-{suffix}.md"
                    path.write_text(
                        _build_frontmatter(c) + c["content"] + "\n",
                        encoding="utf-8",
                    )
                    harvested += 1
        except Exception as e:
            logger.warning("Failed to harvest session %s: %s", session.id, e)
            continue

    return {"status": "success", "harvested": harvested}


def run_harvest_job(
    wiki_base: Path | None = None,
) -> dict[str, Any]:
    """Run the honcho harvest (pull) job.

    Args:
        wiki_base: Base wiki directory

    Returns:
        Dict with harvest results.
    """
    try:
        from honcho import Honcho  # noqa: PLC0415
    except ImportError:
        return {"status": "skipped", "reason": "honcho package not installed"}

    try:
        honcho = Honcho(workspace_id="default")
        return harvest_conclusions(honcho, workspace_id="default", wiki_base=wiki_base)
    except Exception as e:
        logger.error("Honcho harvest failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
