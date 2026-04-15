"""Data models for promotion system."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CrossDomainReference:
    """A reference from one domain to a page in another domain."""

    referring_page_id: str
    referring_domain: str
    referenced_page_id: str
    referenced_domain: str

    def __hash__(self) -> int:
        """Make hashable for set operations."""
        return hash((self.referring_page_id, self.referenced_page_id))

    def __eq__(self, other: object) -> bool:
        """Check equality by pages only (ignore domain info for dedup)."""
        if not isinstance(other, CrossDomainReference):
            return NotImplemented
        return (
            self.referring_page_id == other.referring_page_id
            and self.referenced_page_id == other.referenced_page_id
        )


@dataclass
class PromotionCandidate:
    """A page that is a candidate for promotion to shared."""

    page_id: str
    domain: str
    title: str
    cross_domain_references: int
    total_references: int
    quality_score: float
    page_age_days: int
    promotion_score: float
    should_auto_promote: bool
    should_suggest_promote: bool
    referring_domains: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "page_id": self.page_id,
            "domain": self.domain,
            "title": self.title,
            "cross_domain_references": self.cross_domain_references,
            "total_references": self.total_references,
            "quality_score": self.quality_score,
            "page_age_days": self.page_age_days,
            "promotion_score": self.promotion_score,
            "should_auto_promote": self.should_auto_promote,
            "should_suggest_promote": self.should_suggest_promote,
            "referring_domains": sorted(self.referring_domains),
        }


@dataclass
class PromotionResult:
    """Result of promoting a page to shared."""

    page_id: str
    success: bool
    message: str
    shared_location: str | None = None
    references_updated: int = 0
    review_item_id: str | None = None


@dataclass
class PromotionReport:
    """Report of promotion operations."""

    timestamp: datetime
    total_candidates: int
    auto_promoted: int
    suggested_for_review: int
    promotion_results: list[PromotionResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_candidates": self.total_candidates,
            "auto_promoted": self.auto_promoted,
            "suggested_for_review": self.suggested_for_review,
            "promotion_results": [
                {
                    "page_id": r.page_id,
                    "success": r.success,
                    "message": r.message,
                    "shared_location": r.shared_location,
                    "references_updated": r.references_updated,
                    "review_item_id": r.review_item_id,
                }
                for r in self.promotion_results
            ],
        }
