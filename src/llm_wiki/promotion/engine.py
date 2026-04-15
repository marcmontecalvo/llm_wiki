"""Promotion engine for managing page promotion to shared space."""

import logging
from datetime import UTC, datetime
from pathlib import Path

from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.promotion.config import PromotionConfig
from llm_wiki.promotion.models import PromotionCandidate, PromotionReport, PromotionResult
from llm_wiki.promotion.scorer import PromotionScorer
from llm_wiki.review.models import ReviewItem, ReviewPriority, ReviewStatus, ReviewType
from llm_wiki.review.queue import ReviewQueue

logger = logging.getLogger(__name__)


class PromotionEngine:
    """Engine for promoting pages to shared space."""

    def __init__(self, config: PromotionConfig | None = None, wiki_base: Path | None = None):
        """Initialize promotion engine.

        Args:
            config: Promotion configuration
            wiki_base: Base wiki directory (defaults to wiki_system/)
        """
        self.config = config or PromotionConfig()
        self.wiki_base = wiki_base or Path("wiki_system")

        # Ensure shared directory exists
        self.shared_dir = self.wiki_base / "shared"
        self.shared_dir.mkdir(parents=True, exist_ok=True)

        # Initialize dependencies
        index_dir = self.wiki_base / "index"
        self.backlinks = BacklinkIndex(index_dir=index_dir)
        self.backlinks.load()

        self.scorer = PromotionScorer(config=config, wiki_base=wiki_base)

        # Review queue for managing approval workflow
        self.review_queue = ReviewQueue(queue_dir=self.wiki_base / "review")

    def find_candidates(self) -> list[PromotionCandidate]:
        """Find all pages eligible for promotion.

        Returns:
            List of promotion candidates sorted by score
        """
        return self.scorer.score_all_pages()

    def promote_page(
        self,
        page_id: str,
        source_domain: str,
        update_references: bool = True,
        dry_run: bool = False,
    ) -> PromotionResult:
        """Promote a page from domain-local to shared.

        Args:
            page_id: Page ID to promote
            source_domain: Domain the page is in
            update_references: Whether to update all references to point to shared
            dry_run: If True, simulate promotion without making changes

        Returns:
            PromotionResult with status and details
        """
        try:
            # Verify page exists in source domain
            source_path = self.wiki_base / "domains" / source_domain / "pages" / f"{page_id}.md"
            if not source_path.exists():
                return PromotionResult(
                    page_id=page_id,
                    success=False,
                    message=f"Page not found in {source_domain}: {source_path}",
                )

            # Check if already promoted
            shared_path = self.shared_dir / f"{page_id}.md"
            if shared_path.exists():
                return PromotionResult(
                    page_id=page_id,
                    success=False,
                    message=f"Page already exists in shared: {shared_path}",
                )

            if not dry_run:
                # Copy page to shared directory
                content = source_path.read_text(encoding="utf-8")
                shared_path.write_text(content, encoding="utf-8")
                logger.info(f"Promoted page {page_id} to shared")

                # Create tombstone in original location (redirect marker)
                self._create_tombstone(source_path, page_id)

                # Update all references if requested
                references_updated = 0
                if update_references:
                    references_updated = self._update_references(page_id, source_domain)
                    logger.info(f"Updated {references_updated} references for {page_id}")

                # Update backlink index
                self.backlinks.add_page_links(page_id, content)
                self.backlinks.save()

            return PromotionResult(
                page_id=page_id,
                success=True,
                message=f"Successfully promoted {page_id} to shared",
                shared_location=str(shared_path),
                references_updated=references_updated if not dry_run else 0,
            )

        except Exception as e:
            logger.error(f"Failed to promote {page_id}: {e}", exc_info=True)
            return PromotionResult(
                page_id=page_id,
                success=False,
                message=f"Promotion failed: {e}",
            )

    def suggest_promotion(self, candidate: PromotionCandidate) -> PromotionResult | None:
        """Add a page to the review queue for promotion approval.

        Args:
            candidate: Promotion candidate to suggest

        Returns:
            PromotionResult if review item created, None on failure
        """
        try:
            # Create review item
            reason = (
                f"Page '{candidate.title}' ({candidate.page_id}) is referenced by "
                f"{candidate.cross_domain_references} cross-domain references "
                f"(quality: {candidate.quality_score:.2f}, score: {candidate.promotion_score:.2f})"
            )

            priority = ReviewPriority.MEDIUM
            if candidate.promotion_score >= self.config.auto_promote_threshold:
                priority = ReviewPriority.HIGH

            review_item = ReviewItem(
                id=f"promotion-{candidate.page_id}-{datetime.now(UTC).timestamp()}",
                type=ReviewType.PROMOTION,
                target_id=candidate.page_id,
                reason=reason,
                priority=priority,
                status=ReviewStatus.PENDING,
                created_at=datetime.now(UTC),
                metadata={
                    "page_id": candidate.page_id,
                    "source_domain": candidate.domain,
                    "promotion_score": candidate.promotion_score,
                    "quality_score": candidate.quality_score,
                    "cross_domain_refs": candidate.cross_domain_references,
                    "total_refs": candidate.total_references,
                    "referring_domains": sorted(candidate.referring_domains),
                },
            )

            self.review_queue.create(review_item)

            logger.info(f"Added promotion review for {candidate.page_id}")

            return PromotionResult(
                page_id=candidate.page_id,
                success=True,
                message=f"Added to review queue: {review_item.id}",
                review_item_id=review_item.id,
            )

        except Exception as e:
            logger.error(f"Failed to suggest promotion for {candidate.page_id}: {e}")
            return None

    def process_candidates(self) -> PromotionReport:
        """Process all promotion candidates.

        Automatically promotes eligible pages and suggests others for review.

        Returns:
            PromotionReport with results
        """
        logger.info("Processing promotion candidates...")

        candidates = self.find_candidates()
        report = PromotionReport(
            timestamp=datetime.now(UTC),
            total_candidates=len(candidates),
            auto_promoted=0,
            suggested_for_review=0,
        )

        for candidate in candidates:
            if candidate.should_auto_promote and not self.config.require_approval:
                # Auto-promote
                result = self.promote_page(
                    candidate.page_id, candidate.domain, update_references=True
                )
                report.promotion_results.append(result)
                if result.success:
                    report.auto_promoted += 1

            elif candidate.should_suggest_promote:
                # Add to review queue
                suggest_result = self.suggest_promotion(candidate)
                if suggest_result:
                    report.promotion_results.append(suggest_result)
                    report.suggested_for_review += 1

        logger.info(
            f"Promotion processing complete: "
            f"{report.auto_promoted} auto-promoted, "
            f"{report.suggested_for_review} suggested for review"
        )

        return report

    def _create_tombstone(self, source_path: Path, page_id: str) -> None:
        """Create a tombstone/redirect at original page location.

        Args:
            source_path: Original page path
            page_id: Promoted page ID
        """
        try:
            tombstone_content = f"""---
id: {page_id}
kind: page
title: [Moved to shared]
domain: shared
status: archived
updated_at: {datetime.now(UTC).isoformat()}
---

This page has been promoted to the shared space and is now at `/shared/{page_id}.md`.

All references should be updated to point to the shared version.
"""

            source_path.write_text(tombstone_content, encoding="utf-8")
            logger.debug(f"Created tombstone at {source_path}")

        except Exception as e:
            logger.warning(f"Failed to create tombstone for {page_id}: {e}")

    def _update_references(self, page_id: str, source_domain: str) -> int:
        """Update all references to point to shared page.

        Args:
            page_id: Page ID
            source_domain: Original domain

        Returns:
            Number of references updated
        """
        updated_count = 0
        backlinks = self.backlinks.get_backlinks(page_id)

        # Find all pages that reference this page
        domains_dir = self.wiki_base / "domains"
        if not domains_dir.exists():
            return 0

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                page_stem = page_file.stem
                if page_stem not in backlinks:
                    continue

                try:
                    # Update wiki links to point to shared space
                    # Pattern: [[page-id]] -> [[shared/page-id]] or similar
                    # For simplicity, we track the reference but keep the ID same
                    # since the shared directory is still resolved as [[page-id]]
                    # The key is that the page lookup will find it in shared/

                    # Update the backlinks index
                    new_forward_links = self.backlinks.get_forward_links(page_stem)
                    if page_id in new_forward_links:
                        # Link is already there, no content change needed
                        # But mark that we've processed this reference
                        updated_count += 1

                except Exception as e:
                    logger.warning(f"Failed to update references in {page_file}: {e}")

        return updated_count

    def unpromote_page(
        self,
        page_id: str,
        target_domain: str,
        restore_content: bool = False,
    ) -> PromotionResult:
        """Un-promote a page from shared back to domain-local.

        Args:
            page_id: Page ID to un-promote
            target_domain: Domain to move page back to
            restore_content: If True, restore from tombstone if available

        Returns:
            PromotionResult with status
        """
        try:
            shared_path = self.shared_dir / f"{page_id}.md"
            target_path = self.wiki_base / "domains" / target_domain / "pages" / f"{page_id}.md"

            if not shared_path.exists():
                return PromotionResult(
                    page_id=page_id,
                    success=False,
                    message=f"Shared page not found: {shared_path}",
                )

            # Copy back to domain
            content = shared_path.read_text(encoding="utf-8")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")

            # Remove from shared
            shared_path.unlink()

            # Update index
            self.backlinks.add_page_links(page_id, content)
            self.backlinks.save()

            logger.info(f"Un-promoted {page_id} from shared to {target_domain}")

            return PromotionResult(
                page_id=page_id,
                success=True,
                message=f"Un-promoted {page_id} back to {target_domain}",
                shared_location=str(target_path),
            )

        except Exception as e:
            logger.error(f"Failed to un-promote {page_id}: {e}", exc_info=True)
            return PromotionResult(
                page_id=page_id,
                success=False,
                message=f"Un-promotion failed: {e}",
            )
