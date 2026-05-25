"""Synthesis cache daemon job.

Finds frequently-repeated queries in query_log.db and generates synthesis
cache pages for them.

Gated by features.synthesis_cache in daemon.yaml.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from llm_wiki.paths import resolve_wiki_base

logger = logging.getLogger(__name__)


def run_synthesis_cache_job(
    wiki_base: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the synthesis cache job.

    Reads query_log.db for repeated queries, generates synthesis pages
    in the shared/synthesis/ directory for candidates meeting the threshold.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)
        dry_run: If True, report candidates without writing

    Returns:
        Dictionary with job execution statistics
    """
    from llm_wiki.synthesis.cache import SynthesisCacheJob  # noqa: PLC0415

    wiki_base = resolve_wiki_base(wiki_base)
    log_db = wiki_base / "state" / "query_log.db"

    # Load config values — use defaults if not available
    from llm_wiki.config.loader import load_config  # noqa: PLC0415

    try:
        _cfg = load_config("config")
        del _cfg  # Config loaded for validation; cache uses DB lookup instead
        min_hits = 5  # configurable via daemon config as needed
        window_days = 30
    except Exception:
        min_hits = 5
        window_days = 30

    cache_job = SynthesisCacheJob(
        wiki_base=wiki_base,
        log_db=log_db,
        min_hits=min_hits,
        window_days=window_days,
    )

    candidates = cache_job.get_candidates()
    created = 0
    skipped = 0
    failed = 0

    if not candidates:
        logger.info("No synthesis cache candidates found")
        return {
            "status": "success",
            "candidates": 0,
            "created": 0,
            "skipped": 0,
            "failed": 0,
            "dry_run": dry_run,
        }

    logger.info("Found %d synthesis cache candidate(s)", len(candidates))

    for candidate in candidates:
        existing = cache_job.get_existing_synthesis_page(candidate.query_hash)
        if existing and existing.exists():
            # Check if regeneration is needed (stale check)
            try:
                if cache_job.regenerate_if_stale(existing, candidate):
                    created += 1
                    logger.info("Regenerated: %s", existing)
                else:
                    skipped += 1
            except Exception as e:
                logger.warning("Could not check staleness for hash %s: %s", candidate.query_hash, e)
                skipped += 1
            continue

        if dry_run:
            skipped += 1
            logger.info("[DRY RUN] Would create cache page for: %s", candidate.query_text)
            continue

        result = cache_job.generate_synthesis_page(candidate)
        if result:
            created += 1
        else:
            failed += 1

    logger.info(
        "Synthesis cache job complete: %d created, %d skipped, %d failed",
        created,
        skipped,
        failed,
    )

    return {
        "status": "success" if failed == 0 else "partial",
        "candidates": len(candidates),
        "created": created,
        "skipped": skipped,
        "failed": failed,
        "dry_run": dry_run,
    }


def run_synthesis_cache_dry_run(wiki_base: Path | None = None) -> dict[str, Any]:
    """Run synthesis cache job in dry-run mode (preview only)."""
    return run_synthesis_cache_job(wiki_base=wiki_base, dry_run=True)
