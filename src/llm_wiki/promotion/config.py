"""Configuration for promotion system."""

from pydantic import BaseModel, Field


class PromotionConfig(BaseModel):
    """Configuration for page promotion to shared space."""

    auto_promote_threshold: float = Field(
        default=10.0, ge=0.0, description="Promotion score threshold for auto-promotion"
    )
    suggest_promote_threshold: float = Field(
        default=5.0, ge=0.0, description="Promotion score threshold for suggesting review"
    )
    min_quality_score: float = Field(
        default=0.6, ge=0.0, le=1.0, description="Minimum quality score for promotion eligibility"
    )
    min_cross_domain_refs: int = Field(
        default=2, ge=1, description="Minimum cross-domain references for promotion consideration"
    )
    require_approval: bool = Field(
        default=True, description="Whether promotion requires manual approval via review queue"
    )

    # Scoring weights
    cross_domain_ref_weight: float = Field(
        default=2.0, description="Weight for cross-domain reference count"
    )
    total_ref_weight: float = Field(default=0.5, description="Weight for total reference count")
    quality_weight: float = Field(default=1.0, description="Weight for quality score")
    age_weight: float = Field(default=0.3, description="Weight for page age factor")
    age_factor_cap_days: int = Field(
        default=365, description="Max age in days to consider for age factor (older = capped)"
    )

    def calculate_age_factor(self, age_days: int) -> float:
        """Calculate age factor (0.0 to 1.0) for a page.

        Newer pages get higher factors.

        Args:
            age_days: Age of the page in days

        Returns:
            Age factor (0.0 to 1.0)
        """
        if age_days <= 0:
            return 1.0
        if age_days >= self.age_factor_cap_days:
            return 0.0

        # Linear decay: newer is better
        return 1.0 - (age_days / self.age_factor_cap_days)
