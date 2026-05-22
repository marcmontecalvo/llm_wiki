"""Cross-domain authority scoring based on backlink analysis.

Computes an authority_score for each page based on the count and domain diversity
of incoming backlinks. Purely algorithmic — no LLM calls.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.utils.frontmatter import parse_frontmatter, write_frontmatter

logger = logging.getLogger(__name__)


def compute_authority_scores(wiki_root: Path) -> dict[str, float]:
    """Compute authority scores for all pages based on cross-domain backlinks.

    Score formula::

        score = sum(1.0 / log2(1 + same_domain_count)) + cross_domain_count * 2.0

    Same-domain links get diminishing returns; cross-domain links get a 2x boost.
    All scores are then normalised to 0.0–1.0 by dividing by the maximum score.

    Args:
        wiki_root: Path to the wiki_system directory.

    Returns:
        Dict mapping page_id to normalised authority score in [0.0, 1.0].
    """
    backlink_index = BacklinkIndex(index_dir=wiki_root / "index")
    backlink_index.rebuild_from_pages(wiki_root)

    domains_dir = wiki_root / "domains"
    if not domains_dir.exists():
        logger.warning("No domains directory found at %s", domains_dir)
        return {}

    # Collect all page ids with their domains from the dirs on disk.
    page_domains: dict[str, str] = {}
    for domain_dir in domains_dir.iterdir():
        if not domain_dir.is_dir():
            continue
        pages_dir = domain_dir / "pages"
        if not pages_dir.exists():
            continue
        for page_file in pages_dir.glob("*.md"):
            try:
                metadata, _ = parse_frontmatter(page_file.read_text(encoding="utf-8"))
                page_id = metadata.get("id", page_file.stem)
                page_domains[page_id] = domain_dir.name
            except Exception:
                page_domains[page_file.stem] = domain_dir.name

    # Build a mapping of page_id -> domain for shared pages too.
    shared_dir = wiki_root / "shared"
    if shared_dir.exists():
        for page_file in shared_dir.glob("*.md"):
            try:
                metadata, _ = parse_frontmatter(page_file.read_text(encoding="utf-8"))
                page_id = metadata.get("id", page_file.stem)
                page_domains[page_id] = "shared"
            except Exception:
                page_domains[page_file.stem] = "shared"

    # For each page that receives backlinks, group by referring page's domain.
    scores: dict[str, float] = {}
    for page_id in page_domains:
        backlinks = backlink_index.get_backlinks(page_id)
        if not backlinks:
            continue

        same_count = 0
        cross_count = 0
        page_domain = page_domains.get(page_id, "unknown")
        ref_domains: dict[str, int] = {}
        for ref_id in backlinks:
            ref_domain = page_domains.get(ref_id, "unknown")
            ref_domains[ref_domain] = ref_domains.get(ref_domain, 0) + 1

        for domain, cnt in ref_domains.items():
            if domain == page_domain:
                same_count += cnt
            else:
                cross_count += cnt

        score = 0.0
        if same_count > 0:
            score += sum(
                1.0 / math.log2(1 + ref_domains.get(d, 0)) for d in ref_domains if d == page_domain
            )
        score += cross_count * 2.0
        scores[page_id] = score

    # Also zero-score every page that has zero backlinks.
    for pid in page_domains:
        if pid not in scores:
            scores[pid] = 0.0

    # Normalize to 0.0–1.0.
    max_score = max(scores.values()) if scores else 1.0
    if max_score > 0.0:
        return {pid: s / max_score for pid, s in scores.items()}
    return dict.fromkeys(scores, 0.0)


def write_authority_scores(wiki_root: Path, scores: dict[str, float]) -> int:
    """Write authority_score into page frontmatter for every page.

    Only touches files whose scores changed (value moved) or are newly present.
    Pages with zero score get ``authority_score: 0.0`` written so the field is
    always present.

    Args:
        wiki_root: Path to wiki_system.
        scores: Mapping of page_id -> authority_score.

    Returns:
        Number of files actually written.
    """
    written = 0
    domains_dir = wiki_root / "domains"
    shared_dir = wiki_root / "shared"

    target_dirs: list[Path] = []
    if domains_dir.exists():
        for d in domains_dir.iterdir():
            if d.is_dir():
                target_dirs.append(d / "pages")
    if shared_dir.exists():
        target_dirs.append(shared_dir)

    for pages_dir in target_dirs:
        if not pages_dir.exists():
            continue
        for page_file in pages_dir.glob("*.md"):
            try:
                page_id = page_file.stem
                score = scores.get(page_id, 0.0)
                content = page_file.read_text(encoding="utf-8")
                fm, body = parse_frontmatter(content)
                if fm.get("authority_score") != score:
                    fm["authority_score"] = score
                    new_content = write_frontmatter(fm, body)
                    _atomic_write(page_file, new_content)
                    written += 1
            except Exception:
                continue

    logger.info("Wrote authority_score to %d pages", written)
    return written


def _atomic_write(path: Path, content: str) -> None:
    """Write *content* to *path* atomically."""
    import os
    import tempfile

    fd = tempfile.NamedTemporaryFile(
        "w", dir=path.parent, delete=False, suffix=".tmp", encoding="utf-8"
    )
    try:
        fd.write(content)
        fd.close()
        os.replace(fd.name, path)
    except BaseException:
        try:
            os.unlink(fd.name)
        except OSError:
            pass
        raise
