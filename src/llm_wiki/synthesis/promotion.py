"""Entity promotion to cross-domain status.

Promotes entities that appear in multiple domains with high confidence
to shared cross-domain pages.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from llm_wiki.models.config import PromotionConfig


@dataclass
class PromotionCandidate:
    """An entity eligible for cross-domain promotion."""

    page_id: str
    domain: str
    title: str
    confidence: float
    domains_appearing: int = 0
    page_file: Path | None = None


@dataclass
class PromotionReport:
    """Result of a promotion run."""

    total_candidates: int = 0
    auto_promoted: int = 0
    suggested_for_review: int = 0
    skipped: int = 0


class PromotionEngine:
    """Detects and promotes cross-domain entities.

    An entity qualifies when it appears in >= ::config.min_domains ::domains
    with average confidence >= ::config.min_confidence.
    """

    def __init__(
        self,
        wiki_base: Path | None = None,
        config: PromotionConfig | None = None,
    ):
        self.wiki_base = wiki_base or Path("wiki_system")
        self.config = config or PromotionConfig()

    # ── detection ──────────────────────────────────────────────────

    def _enumerate_pages(self) -> list[dict]:
        """Read all page files and return their frontmatter dicts."""
        pages: list[dict] = []
        domains_dir = self.wiki_base / "domains"
        if not domains_dir.exists():
            return pages
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue
            for page_file in pages_dir.glob("*.md"):
                try:
                    from llm_wiki.utils.frontmatter import (  # noqa: PLC0415
                        parse_frontmatter,
                    )

                    metadata, _ = parse_frontmatter(page_file.read_text(encoding="utf-8"))
                    metadata["_page_file"] = page_file
                    metadata["_domain"] = domain_dir.name
                    pages.append(metadata)
                except Exception:
                    continue
        return pages

    def _find_entities(self, pages: list[dict]) -> list[PromotionCandidate]:
        """Group pages by entity identity and find promotion candidates."""
        # Build a map of normalized title -> pages
        title_map: dict[str, list[dict]] = {}
        for page in pages:
            title = page.get("title", "").strip().lower()
            if not title:
                continue
            title_map.setdefault(title, []).append(page)

        candidates: list[PromotionCandidate] = []
        promoted_page_ids: set[str] = set()

        for _title, group in title_map.items():
            if len(group) < self.config.min_domains:
                continue

            # Check that pages appear in >= min_domains distinct domains
            domains_seen: set[str] = set()
            confidences: list[float] = []
            for page in group:
                pages_id = page.get("id")
                if pages_id in promoted_page_ids:
                    continue
                domains_seen.add(page.get("_domain", "unknown"))
                confidences.append(page.get("confidence", 0.0))

            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            domain_count = len(domains_seen)

            if (
                domain_count >= self.config.min_domains
                and avg_confidence >= self.config.min_confidence
            ):
                for page in group:
                    pages_id = page.get("id", "")
                    if pages_id not in promoted_page_ids:
                        candidates.append(
                            PromotionCandidate(
                                page_id=pages_id,
                                domain=page.get("_domain", "unknown"),
                                title=page.get("title", ""),
                                confidence=page.get("confidence", 0.0),
                                domains_appearing=domain_count,
                                page_file=page.get("_page_file"),
                            )
                        )
                        promoted_page_ids.add(pages_id)

        return candidates

    # ── promotion ──────────────────────────────────────────────────

    def _slugify(self, text: str) -> str:
        """Convert text to a URL-safe slug."""
        import re

        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9]+", "-", text)
        return text.strip("-")

    def _atomic_write(self, path: Path, content: str) -> None:
        """Write content to path atomically."""
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

    def _do_promote(self, candidates: list[PromotionCandidate]) -> PromotionReport:
        """Execute the promotion logic for a list of candidates."""
        import frontmatter

        report = PromotionReport(total_candidates=len(candidates))

        if not candidates:
            return report

        # Group candidates by title_similarity
        title_map: dict[str, list[PromotionCandidate]] = {}
        for c in candidates:
            title_map.setdefault(c.title, []).append(c)

        shared_dir = self.wiki_base / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)

        for title, group in title_map.items():
            # Check if already promoted (skip idempotency)
            slug = self._slugify(title)
            shared_file = shared_dir / f"{slug}.md"

            source_pages: list[str] = []
            domains: list[str] = []
            for c in group:
                source_pages.append(c.page_id)
                domains.append(c.domain)

            if shared_file.exists():
                # Already promoted — update source_fields in existing page
                report.skipped += len(group)
                try:
                    existing_fm, existing_body = frontmatter.load(shared_file)
                    if isinstance(existing_fm, dict):
                        existing_fm["source_pages"] = list(set(source_pages))
                        existing_fm["domains"] = list(set(domains))
                        new_content = frontmatter.dumps(
                            frontmatter.Post(existing_body, **existing_fm)
                        )
                        self._atomic_write(shared_file, new_content)
                    else:
                        report.skipped -= 1  # didn't actually update
                except Exception:
                    report.skipped -= 1
                continue

            # Create shared entity page
            now = datetime.now(UTC).isoformat()
            max_confidence = max(c.confidence for c in group)
            share_fm = {
                "id": slug,
                "kind": "entity",
                "title": title,
                "domains": list(set(domains)),
                "promoted_at": now,
                "source_pages": source_pages,
                "confidence": max_confidence,
                "updated_at": now,
            }

            share_body = "# {}\n\nCross-domain entity promoted from: {}\n".format(
                title,
                ", ".join(f"[{sid}]" for sid in source_pages),
            )

            post = frontmatter.Post(share_body, **share_fm)
            self._atomic_write(shared_file, frontmatter.dumps(post))

            # Update source pages: write tombstones
            for c in group:
                page_file = c.page_file
                if not page_file:
                    continue
                try:
                    existing_fm, existing_body = frontmatter.load(page_file)
                    if isinstance(existing_fm, dict):
                        existing_fm["status"] = "archived"
                        existing_fm["promoted_to"] = f"shared/{slug}"
                        new_content = frontmatter.dumps(
                            frontmatter.Post(f"> Promoted to [[{slug}]]", **existing_fm)
                        )
                        self._atomic_write(page_file, new_content)

                        # Remap original page file to archive
                        archive_dir = self.wiki_base / "domains" / c.domain / "archive"
                        archive_dir.mkdir(parents=True, exist_ok=True)
                        archive_file = archive_dir / f"{self._slugify(c.page_id)}.md"
                        try:
                            os.replace(str(page_file), str(archive_file))
                        except OSError:
                            pass
                except Exception:
                    continue

            report.auto_promoted += len(group)

        return report

    # ── public API ─────────────────────────────────────────────────

    def process_candidates(self) -> PromotionReport:
        """Find promotion candidates and process them."""
        pages = self._enumerate_pages()
        candidates = self._find_entities(pages)
        return self._do_promote(candidates)
