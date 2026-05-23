"""Archive service — page archival and staleness-based archiving.

Reads/writes page files via frontmatter utilities and atomic file moves.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter, write_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class ArchiveCandidate:
    """A page eligible for archival."""

    page_id: str
    file_path: Path
    domain: str
    updated_at: str
    age_days: int


def find_page_by_id(page_id: str, wiki_base: Path) -> dict[str, Any] | None:
    """Find a page by its ID across all domains.

    Searches both pages/ and archive/ directories.

    Args:
        page_id: Page identifier
        wiki_base: Base wiki directory

    Returns:
        Dict with page_id, file_path, domain, frontmatter — or None
    """
    domains_dir = wiki_base / "domains"
    if not domains_dir.exists():
        return None

    for domain_dir in sorted(domains_dir.iterdir()):
        if not domain_dir.is_dir() or domain_dir.is_symlink():
            continue

        for subdir in ["pages", "archive"]:
            search_dir = domain_dir / subdir
            if not search_dir.exists():
                continue

            for page_file in sorted(search_dir.glob("*.md")):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)
                    if metadata.get("id", page_file.stem) == page_id:
                        return {
                            "page_id": page_id,
                            "file_path": page_file,
                            "domain": domain_dir.name,
                            "frontmatter": metadata,
                            "body": "",
                            "archived": subdir == "archive",
                        }
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", page_file, e)

    return None


def _get_updated_at_ms(metadata: dict[str, Any]) -> float | None:
    """Extract updated_at timestamp in milliseconds from page frontmatter."""
    raw = metadata.get("updated_at") or metadata.get("updated") or metadata.get("updated_at_ts")
    if raw is None:
        return None
    try:
        if isinstance(raw, datetime):
            return raw.timestamp() * 1000
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw).timestamp() * 1000
            except ValueError:
                return float(raw)
        return float(raw)
    except (ValueError, TypeError):
        return None


def archive_page(page_id: str, wiki_base: Path) -> dict[str, Any]:
    """Archive a page by ID.

    Moves the page from pages/ to archive/ and updates frontmatter.
    Idempotent: if already archived, returns success.

    Args:
        page_id: Page identifier
        wiki_base: Base wiki directory

    Returns:
        Dict with status and details
    """
    candidate = find_page_by_id(page_id, wiki_base)
    if candidate is None:
        return {"status": "error", "error": f"Page not found: {page_id}"}

    file_path: Path = candidate["file_path"]
    domain: str = candidate["domain"]
    frontmatter: dict[str, Any] = candidate["frontmatter"]

    if candidate["archived"]:
        return {"status": "success", "message": "Page is already archived", "page_id": page_id}

    ts = datetime.now(UTC).isoformat()
    frontmatter["archived_at"] = ts

    # Read content BEFORE moving
    content = file_path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(content)
    new_content = write_frontmatter(frontmatter, body)

    archive_dir = wiki_base / "domains" / domain / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / file_path.name

    try:
        dest.write_text(new_content, encoding="utf-8")
        os.remove(str(file_path))
    except OSError as e:
        logger.error("Failed to move %s to archive: %s", file_path, e)
        # Clean up temp write if rename fails
        if dest.exists():
            os.remove(str(dest))
        return {"status": "error", "error": str(e)}

    logger.info("Archived page %s (%s) -> archive/%s", page_id, domain, dest.name)
    return {"status": "success", "message": f"Archived page {page_id}", "page_id": page_id}


def unarchive_page(page_id: str, wiki_base: Path) -> dict[str, Any]:
    """Restore an archived page back to pages/.

    Args:
        page_id: Page identifier
        wiki_base: Base wiki directory

    Returns:
        Dict with status and details
    """
    candidate = find_page_by_id(page_id, wiki_base)
    if candidate is None:
        return {"status": "error", "error": f"Page not found: {page_id}"}

    file_path: Path = candidate["file_path"]

    if not candidate["archived"]:
        return {"status": "error", "error": f"Page is not archived: {page_id}"}

    frontmatter = candidate["frontmatter"]
    frontmatter.pop("archived_at", None)

    # Read content BEFORE moving
    content = file_path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(content)
    new_content = write_frontmatter(frontmatter, body)

    pages_dir = wiki_base / "domains" / candidate["domain"] / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    dest = pages_dir / file_path.name

    try:
        dest.write_text(new_content, encoding="utf-8")
        os.remove(str(file_path))
    except OSError as e:
        logger.error("Failed to restore %s from archive: %s", file_path, e)
        # Clean up temp write if move fails
        if dest.exists():
            os.remove(str(dest))
        return {"status": "error", "error": str(e)}

    logger.info(
        "Unarchived page %s (%s): archive/%s -> pages/%s",
        page_id,
        candidate["domain"],
        file_path.name,
        dest.name,
    )
    return {"status": "success", "message": f"Restored page {page_id}", "page_id": page_id}


def archive_stale_pages(wiki_base: Path, dry_run: bool = False) -> dict[str, Any]:
    """Archive pages that exceed their domain's staleness threshold.

    Args:
        wiki_base: Base wiki directory
        dry_run: If True, compute candidates without moving

    Returns:
        Dict with status and counts
    """
    catalog: list[ArchiveCandidate] = []
    domains_dir = wiki_base / "domains"
    if not domains_dir.exists():
        return {"status": "success", "archived": 0, "skipped": 0, "dry_run": dry_run}

    # Try loading per-domain staleness threshold from config
    config_dir = wiki_base / "config"
    default_threshold_days = 90
    try:
        from llm_wiki.config.loader import load_config  # noqa: PLC0415

        cfg = load_config(config_dir)
        # cfg.domains is DomainsYAML with .domains: list[DomainConfig]
        # cfg.daemon is DaemonYAML with .daemon: DaemonConfig
        _daemon = getattr(cfg.daemon, "daemon", None)
        default_threshold_days = getattr(_daemon, "staleness_threshold_days", 90) if _daemon else 90
    except Exception:
        pass

    for domain_dir in sorted(domains_dir.iterdir()):
        if not domain_dir.is_dir() or domain_dir.is_symlink():
            continue

        domain_name = domain_dir.name
        pages_dir = domain_dir / "pages"
        if not pages_dir.exists():
            continue

        # Override staleness_threshold_days from domain-level config
        staleness_days = default_threshold_days

        cutoff_ms = (datetime.now(UTC).timestamp() - (staleness_days * 86400)) * 1000

        for page_file in sorted(pages_dir.glob("*.md")):
            try:
                content = page_file.read_text(encoding="utf-8")
                metadata, _ = parse_frontmatter(content)
                updated_ms = _get_updated_at_ms(metadata)
                if updated_ms is None or updated_ms > cutoff_ms:
                    continue

                page_id = metadata.get("id", page_file.stem)
                age_days = int((datetime.now(UTC).timestamp() * 1000 - updated_ms) / 86400000)
                catalog.append(
                    ArchiveCandidate(
                        page_id=page_id,
                        file_path=page_file,
                        domain=domain_name,
                        updated_at=str(metadata.get("updated_at", "")),
                        age_days=age_days,
                    )
                )
            except Exception as e:
                logger.warning("Failed to check staleness for %s: %s", page_file, e)

    archived = 0
    skipped = 0

    for c in catalog:
        if dry_run:
            skipped += 1
            continue
        result = archive_page(c.page_id, wiki_base)
        if result.get("status") == "success":
            archived += 1
        else:
            skipped += 1

    return {
        "status": "success",
        "archived": archived,
        "skipped": skipped,
        "total_candidates": len(catalog),
        "dry_run": dry_run,
    }
