"""Promotion scoring algorithm."""

import logging
from datetime import UTC, datetime
from pathlib import Path

from llm_wiki.governance.quality import QualityScorer
from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.promotion.config import PromotionConfig
from llm_wiki.promotion.models import CrossDomainReference, PromotionCandidate
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class PromotionScorer:
    """Scorer for determining page promotion priority."""

    def __init__(self, config: PromotionConfig | None = None, wiki_base: Path | None = None):
        """Initialize promotion scorer.

        Args:
            config: Promotion configuration (uses defaults if not provided)
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.config = config or PromotionConfig()
        self.wiki_base = wiki_base or Path("wiki_system")

        # Initialize supporting indices
        index_dir = self.wiki_base / "index"
        self.backlinks = BacklinkIndex(index_dir=index_dir)
        self.backlinks.load()

        self.quality_scorer = QualityScorer()

    def score_page(self, page_id: str, page_path: Path, domain: str) -> PromotionCandidate | None:
        """Score a single page for promotion eligibility.

        Args:
            page_id: Page identifier
            page_path: Path to page file
            domain: Domain the page belongs to

        Returns:
            PromotionCandidate if eligible, None otherwise
        """
        try:
            # Read page metadata
            content = page_path.read_text(encoding="utf-8")
            metadata, body = parse_frontmatter(content)

            title = metadata.get("title", page_id)

            # Get quality score
            quality_report = self.quality_scorer.score_page(page_path)
            quality_score = quality_report.score

            # Skip if below minimum quality
            if quality_score < self.config.min_quality_score:
                return None

            # Get page creation date
            created_at_str = metadata.get("created_at")
            created_at = None
            if created_at_str:
                try:
                    if isinstance(created_at_str, str):
                        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    elif isinstance(created_at_str, datetime):
                        created_at = created_at_str
                except (ValueError, AttributeError):
                    pass

            age_days = 0
            if created_at:
                age_days = (datetime.now(UTC) - created_at).days

            # Get reference counts
            backlinks_list = self.backlinks.get_backlinks(page_id)
            total_references = len(backlinks_list)

            # Find cross-domain references
            cross_domain_refs = self._find_cross_domain_references(page_id, backlinks_list, domain)
            cross_domain_count = len(cross_domain_refs)

            # Skip if below minimum cross-domain references
            if cross_domain_count < self.config.min_cross_domain_refs:
                return None

            # Calculate promotion score
            age_factor = self.config.calculate_age_factor(age_days)

            promotion_score = (
                cross_domain_count * self.config.cross_domain_ref_weight
                + total_references * self.config.total_ref_weight
                + quality_score * self.config.quality_weight
                + age_factor * self.config.age_weight
            )

            # Determine promotion eligibility
            should_auto_promote = promotion_score >= self.config.auto_promote_threshold
            should_suggest_promote = promotion_score >= self.config.suggest_promote_threshold

            # Extract referring domains from cross-domain references
            referring_domains = {ref.referring_domain for ref in cross_domain_refs}

            candidate = PromotionCandidate(
                page_id=page_id,
                domain=domain,
                title=title,
                cross_domain_references=cross_domain_count,
                total_references=total_references,
                quality_score=quality_score,
                page_age_days=age_days,
                promotion_score=promotion_score,
                should_auto_promote=should_auto_promote,
                should_suggest_promote=should_suggest_promote,
                referring_domains=referring_domains,
            )

            logger.debug(
                f"Scored {page_id}: {promotion_score:.2f} (cross-domain: {cross_domain_count})"
            )

            return candidate

        except Exception as e:
            logger.error(f"Failed to score page {page_id}: {e}")
            return None

    def score_all_pages(self) -> list[PromotionCandidate]:
        """Score all pages in the wiki.

        Returns:
            List of promotion candidates (sorted by promotion score, descending)
        """
        candidates: list[PromotionCandidate] = []

        domains_dir = self.wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return candidates

        # Scan all domain pages
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            domain_id = domain_dir.name
            pages_dir = domain_dir / "pages"

            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                page_id = page_file.stem

                # Skip pages already in shared
                if self._is_shared_page(page_id):
                    continue

                candidate = self.score_page(page_id, page_file, domain_id)
                if candidate:
                    candidates.append(candidate)

        # Sort by promotion score (highest first)
        candidates.sort(key=lambda c: c.promotion_score, reverse=True)

        logger.info(f"Scored {len(candidates)} promotion candidates")

        return candidates

    def _find_cross_domain_references(
        self, page_id: str, backlink_ids: list[str], target_domain: str
    ) -> list[CrossDomainReference]:
        """Find cross-domain references to a page.

        Args:
            page_id: Target page ID
            backlink_ids: List of page IDs that reference this page
            target_domain: Domain of the target page

        Returns:
            List of cross-domain references
        """
        cross_domain_refs: set[CrossDomainReference] = set()

        for referring_id in backlink_ids:
            # Find which domain contains this referring page
            referring_domain = self._find_page_domain(referring_id)

            if referring_domain and referring_domain != target_domain:
                ref = CrossDomainReference(
                    referring_page_id=referring_id,
                    referring_domain=referring_domain,
                    referenced_page_id=page_id,
                    referenced_domain=target_domain,
                )
                cross_domain_refs.add(ref)

        return list(cross_domain_refs)

    def _find_page_domain(self, page_id: str) -> str | None:
        """Find which domain contains a page.

        Args:
            page_id: Page identifier

        Returns:
            Domain ID or None if not found
        """
        domains_dir = self.wiki_base / "domains"

        if not domains_dir.exists():
            return None

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            page_file = domain_dir / "pages" / f"{page_id}.md"
            if page_file.exists():
                return domain_dir.name

        return None

    def _is_shared_page(self, page_id: str) -> bool:
        """Check if a page is already in the shared directory.

        Args:
            page_id: Page identifier

        Returns:
            True if page is in shared/, False otherwise
        """
        shared_dir = self.wiki_base / "shared"
        return (shared_dir / f"{page_id}.md").exists()
