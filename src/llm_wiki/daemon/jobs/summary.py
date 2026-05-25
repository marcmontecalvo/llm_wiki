"""Cross-domain summary page generation.

Scans wiki_system/shared/ for promoted entities and generates summary
pages (kind: concept) that aggregate claims from all contributing domains.
"""

from __future__ import annotations

import logging
import os
import re
import string
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import frontmatter

from llm_wiki.models.config import SummaryConfig
from llm_wiki.paths import resolve_wiki_base
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


@dataclass
class Claim:
    """A single claim extracted from a page."""

    text: str
    confidence: float
    trust_tag: str = ""
    source_page_id: str = ""


@dataclass
class SummaryReport:
    """Result of a summary generation run."""

    total_entities: int = 0
    summaries_generated: int = 0
    summaries_updated: int = 0
    summaries_archived: int = 0
    errors: int = 0


class CrossDomainSummaryJob:
    """Generates summary pages for cross-domain promoted entities."""

    def __init__(
        self,
        wiki_base: Path | None = None,
        config: SummaryConfig | None = None,
        llm_extraction: bool = False,
    ):
        self.wiki_base = resolve_wiki_base(wiki_base)
        self.config = config or SummaryConfig()
        self.llm_extraction = llm_extraction

    # ── entity discovery ───────────────────────────────────────────

    def _find_shared_entities(self) -> list[dict]:
        """Find all shared pages with kind: entity."""
        entities: list[dict] = []
        shared_dir = self.wiki_base / "shared"
        if not shared_dir.exists():
            return entities

        for page_file in sorted(shared_dir.glob("*.md")):
            try:
                fm, _ = parse_frontmatter(page_file.read_text(encoding="utf-8"))
                if fm.get("kind") == "entity":
                    fm["_page_file"] = page_file
                    entities.append(fm)
            except Exception:
                continue
        return entities

    # ── claim aggregation ──────────────────────────────────────────

    def _normalize_text(self, text: str) -> str:
        """Normalize claim text for deduplication."""
        text = text.strip().lower()
        text = text.translate(str.maketrans("", "", string.punctuation))
        return " ".join(text.split())

    def _extract_claims(self, page_frontmatter: dict) -> list[Claim]:
        """Extract claims from page frontmatter."""
        claims: list[Claim] = []
        for claim in page_frontmatter.get("claims", []):
            if not isinstance(claim, dict):
                continue
            text = claim.get("text", "")
            if not text:
                continue
            claims.append(
                Claim(
                    text=text,
                    confidence=claim.get("confidence", 0.0),
                    trust_tag=claim.get("trust_tag", ""),
                    source_page_id=page_frontmatter.get("id", ""),
                )
            )
        return claims

    def _deduplicate_claims(self, raw_claims: list[Claim], top_n: int) -> list[str]:
        """Sort by confidence, deduplicate by normalized text, return top-N claim texts."""
        sorted_claims = sorted(raw_claims, key=lambda c: c.confidence, reverse=True)

        seen: set[str] = set()
        deduplicated: list[str] = []
        for claim in sorted_claims:
            normalized = self._normalize_text(claim.text)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduplicated.append(claim.text)
            if len(deduplicated) >= top_n:
                break

        return deduplicated

    # ── LLM synthesis ──────────────────────────────────────────────

    def _synthesize_with_llm(self, claims: list[str], title: str) -> str:
        """Attempt LLM-based summarization of claims. Falls back to claim digest."""
        system_prompt = (
            "You are a knowledge synthesizer. "
            "Given a list of claims about an entity, produce a concise 2-3 sentence summary "
            "that captures what is known about the entity across all sources."
        )
        claim_body = "\n".join(f"- {c}" for c in claims)
        user_prompt = f"Entity: {title}\n\nClaims:\n{claim_body}\n\nProduce a 2-3 sentence summary."

        try:
            from llm_wiki.models.client import (  # type: ignore[import-not-found]
                create_model_client,
            )
            from llm_wiki.models.config import (  # type: ignore[import-not-found]
                load_models_config,
            )

            models_config = load_models_config(Path("config/models.yaml"))
            provider_config = models_config.get_provider("extraction")
            client = create_model_client(provider_config)
            response = client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.strip()
        except Exception as e:
            logger.warning(
                "LLM synthesis failed for '%s': %s — falling back to claim digest", title, e
            )
            return "\n".join(f"- {c}" for c in claims)

    # ── summary generation ─────────────────────────────────────────

    def _slugify(self, text: str) -> str:
        """Convert text to a URL-safe slug."""
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

    # ── promotion threshold check ──────────────────────────────────

    def _check_entity_healthy(self, entity_fm: dict) -> bool:
        """Check if an entity's source pages still meet promotion threshold.

        An entity remains healthy if its source pages (from source_pages frontmatter)
        still reference published pages in >= 2 distinct domains.
        """
        domains = entity_fm.get("domains", [])
        source_pages = entity_fm.get("source_pages", [])
        if not source_pages:
            return False

        # Check each domain still has published pages
        healthy = 0
        for domain_id in domains:
            for page_id in source_pages:
                fm = self._try_load_source_page(page_id)
                if fm is not None and fm.get("status") not in ("archived",):
                    # Verify source page actually belongs to this domain
                    if fm.get("domain") == domain_id:
                        healthy += 1
                        break  # Only count one page per domain

        return healthy >= 2

    def _try_load_source_page(self, page_id: str) -> dict[str, Any] | None:
        """Try to load a source page frontmatter. Returns frontmatter dict or None."""
        # Check shared first
        shared_file = self.wiki_base / "shared" / f"{page_id}.md"
        if shared_file.exists():
            try:
                content = shared_file.read_text(encoding="utf-8")
                fm, _ = parse_frontmatter(content)
                return fm
            except Exception:
                pass

        # Check each domain
        domains_dir = self.wiki_base / "domains"
        if not domains_dir.exists():
            return None

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            page_file = domain_dir / "pages" / f"{page_id}.md"
            if page_file.exists():
                try:
                    content = page_file.read_text(encoding="utf-8")
                    fm, _ = parse_frontmatter(content)
                    return fm
                except Exception:
                    pass

        return None

    def _archive_summary(self, summary_file: Path) -> None:
        """Archive a summary page to wiki_system/archive/shared/."""
        archive_dir = self.wiki_base / "archive" / "shared"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_file = archive_dir / summary_file.name
        try:
            summary_file.replace(archive_file)
            logger.info("Archived summary page: %s -> %s", summary_file, archive_file)
        except OSError:
            try:
                summary_file.unlink(missing_ok=True)
            except OSError:
                pass

    # ── public API ─────────────────────────────────────────────────

    def process_entities(self) -> SummaryReport:
        """Scan for shared entities and generate/update summary pages."""
        report = SummaryReport()
        entities = self._find_shared_entities()
        report.total_entities = len(entities)

        summary_dir = self.wiki_base / "shared"
        summary_dir.mkdir(parents=True, exist_ok=True)

        for entity_fm in entities:
            source_pages = entity_fm.get("source_pages", [])
            domains = entity_fm.get("domains", [])
            title = entity_fm.get("title", "Unknown")

            # Check if entity still meets promotion threshold
            if not self._check_entity_healthy(entity_fm):
                summary_file = summary_dir / f"{self._slugify(title)}-summary.md"
                if summary_file.exists():
                    self._archive_summary(summary_file)
                    report.summaries_archived += 1
                continue

            # Collect claims from all source pages
            all_claims: list[Claim] = []
            for page_id in source_pages:
                fm = self._try_load_source_page(page_id)
                if fm is None:
                    continue
                all_claims.extend(self._extract_claims(fm))

            # Deduplicate and select top-N claims
            claim_texts = self._deduplicate_claims(all_claims, self.config.top_n)

            # Generate or update summary
            slug = f"{self._slugify(title)}-summary"
            summary_file = summary_dir / f"{slug}.md"

            model = "llm_synthesis" if self.llm_extraction else "claim_digest"

            if self.llm_extraction and claim_texts:
                summary_body = self._synthesize_with_llm(claim_texts, title)
            else:
                summary_body = "\n".join(f"- {c}" for c in claim_texts)

            now = datetime.now(UTC).isoformat()
            summary_fm = {
                "id": slug,
                "kind": "concept",
                "title": f"{title} — Summary",
                "domains": list(set(domains)) if domains else [],
                "generated_at": now,
                "model": model,
                "source_count": len(claim_texts),
                "updated_at": now,
                "authority_score": 1.0,
            }

            # Ensure kind=concept is included in frontmatter
            if not (isinstance(summary_fm, dict) and summary_fm.get("kind") == "concept"):
                summary_fm["kind"] = "concept"

            post = frontmatter.Post(summary_body, **summary_fm)
            self._atomic_write(summary_file, frontmatter.dumps(post))
            report.summaries_generated += 1

        return report


def run_cross_domain_summary(
    wiki_base: Path | None = None,
) -> dict[str, Any]:
    """Run cross-domain summary generation job.

    This function is called by the daemon scheduler.

    Args:
        wiki_base: Base wiki directory (defaults to wiki_system/)

    Returns:
        Dictionary with summary generation statistics
    """
    job = CrossDomainSummaryJob(wiki_base=wiki_base)
    try:
        report = job.process_entities()
        stats = {
            "status": "success",
            "total_entities": report.total_entities,
            "summaries_generated": report.summaries_generated,
            "summaries_updated": report.summaries_updated,
            "summaries_archived": report.summaries_archived,
        }
        logger.info(f"Cross-domain summary generation complete: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Cross-domain summary generation failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "total_entities": 0,
            "summaries_generated": 0,
            "summaries_updated": 0,
            "summaries_archived": 0,
        }
