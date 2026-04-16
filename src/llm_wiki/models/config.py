"""Configuration schemas using Pydantic."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class DomainConfig(BaseModel):
    """Configuration for a single wiki domain."""

    id: str = Field(..., description="Domain identifier (lowercase-hyphenated)")
    title: str = Field(..., description="Human-readable domain title")
    description: str = Field(..., description="Domain purpose and scope")
    owners: list[str] = Field(default_factory=list, description="Domain owners")
    promote_to_shared: bool = Field(
        default=True, description="Allow promoting content to shared space"
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate domain ID is lowercase-hyphenated."""
        if not v:
            raise ValueError("Domain ID cannot be empty")
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Domain ID must be alphanumeric with hyphens/underscores")
        if v != v.lower():
            raise ValueError("Domain ID must be lowercase")
        return v


class DomainsYAML(BaseModel):
    """Root configuration for domains.yaml."""

    domains: list[DomainConfig] = Field(..., description="List of wiki domains")

    @field_validator("domains")
    @classmethod
    def validate_unique_ids(cls, v: list[DomainConfig]) -> list[DomainConfig]:
        """Ensure domain IDs are unique."""
        ids = [d.id for d in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Domain IDs must be unique")
        return v


class PromotionConfig(BaseModel):
    """Configuration for page promotion."""

    enabled: bool = Field(default=True, description="Enable promotion job")
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


class DaemonConfig(BaseModel):
    """Configuration for the wiki daemon."""

    inbox_poll_seconds: int = Field(default=15, ge=1, description="Seconds between inbox polls")
    retry_failed_ingests_every_minutes: int = Field(
        default=30, ge=1, description="Minutes between retry attempts"
    )
    rebuild_index_every_minutes: int = Field(
        default=30, ge=1, description="Minutes between index rebuilds"
    )
    lint_every_minutes: int = Field(default=60, ge=1, description="Minutes between lint runs")
    stale_check_every_hours: int = Field(
        default=24, ge=1, description="Hours between stale page checks"
    )
    export_every_minutes: int = Field(default=60, ge=1, description="Minutes between export runs")
    promotion_every_hours: int = Field(
        default=24, ge=1, description="Hours between promotion checks"
    )
    max_parallel_jobs: int = Field(default=2, ge=1, le=32, description="Maximum concurrent jobs")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )
    review_queue_enabled: bool = Field(
        default=True, description="Enable review queue for low-confidence content"
    )
    review_queue_every_minutes: int = Field(
        default=30, ge=1, description="Minutes between review queue population runs"
    )
    review_queue_min_page_quality: float = Field(
        default=0.4, ge=0.0, le=1.0, description="Minimum quality threshold for pages"
    )
    review_queue_min_claim_confidence: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Minimum confidence threshold for claims"
    )
    review_queue_max_pending: int = Field(
        default=1000, ge=1, description="Maximum pending items in review queue"
    )
    review_queue_retention_days: int = Field(
        default=30, ge=1, description="Days to keep resolved review items"
    )
    promotion: PromotionConfig = Field(
        default_factory=PromotionConfig, description="Promotion configuration"
    )


class DaemonYAML(BaseModel):
    """Root configuration for daemon.yaml."""

    daemon: DaemonConfig


class SourceRule(BaseModel):
    """Routing rule based on source path matching."""

    match: str = Field(..., description="String to match in source path")
    default_domain: str = Field(..., description="Domain to route to on match")


class RoutingConfig(BaseModel):
    """Configuration for content routing."""

    fallback_domain: str = Field(
        default="general", description="Fallback domain when routing fails"
    )
    confidence_threshold: float = Field(
        default=0.75, ge=0.0, le=1.0, description="Minimum confidence for auto-routing"
    )
    explicit_override_frontmatter_key: str = Field(
        default="domain", description="Frontmatter key for explicit domain override"
    )
    source_rules: list[SourceRule] = Field(
        default_factory=list, description="Source path-based routing rules"
    )


class RoutingYAML(BaseModel):
    """Root configuration for routing.yaml."""

    routing: RoutingConfig


class ModelProviderConfig(BaseModel):
    """Configuration for a model provider."""

    provider: str = Field(..., description="Provider name (local, openai, anthropic, etc.)")
    model: str = Field(..., description="Model identifier")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int | None = Field(default=None, ge=1, description="Max tokens to generate")
    timeout: int = Field(default=30, ge=1, description="Request timeout in seconds")


class ContractsConfig(BaseModel):
    """Configuration for validation contracts."""

    require_schema_validation: bool = Field(
        default=True, description="Require schema validation for all outputs"
    )
    allow_freeform_page_writes: bool = Field(
        default=False, description="Allow freeform page writes without validation"
    )


class ModelsYAML(BaseModel):
    """Root configuration for models.yaml."""

    models: dict[str, ModelProviderConfig] = Field(
        ..., description="Model configurations by purpose (extraction, integration, lint)"
    )
    contracts: ContractsConfig = Field(
        default_factory=ContractsConfig, description="Validation contracts"
    )

    def get_provider(self, purpose: str = "extraction") -> ModelProviderConfig:
        """Get model provider config for a specific purpose.

        Args:
            purpose: Model purpose (extraction, integration, lint, etc.)

        Returns:
            Model provider config

        Raises:
            KeyError: If purpose not found in config
        """
        if purpose not in self.models:
            raise KeyError(f"No model configured for purpose: {purpose}")
        return self.models[purpose]


class WikiConfig(BaseModel):
    """Complete wiki configuration loaded from all YAML files."""

    domains: DomainsYAML
    daemon: DaemonYAML
    routing: RoutingYAML
    models: ModelsYAML


def load_models_config(filepath: Path) -> ModelsYAML:
    """Load models configuration from YAML file.

    Args:
        filepath: Path to models.yaml

    Returns:
        Parsed models configuration

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If YAML is invalid
    """
    if not filepath.exists():
        raise FileNotFoundError(f"Models config not found: {filepath}")

    with filepath.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return ModelsYAML.model_validate(data)
