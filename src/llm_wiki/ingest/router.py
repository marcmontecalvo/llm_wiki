"""Domain routing for wiki content."""

from typing import Any, cast

from llm_wiki.config.loader import WikiConfig
from llm_wiki.models.config import RoutingConfig


class DomainRouter:
    """Routes content to appropriate domains based on rules."""

    def __init__(self, config: WikiConfig):
        """Initialize domain router.

        Args:
            config: Wiki configuration
        """
        self.config = config
        self.routing: RoutingConfig = config.routing.routing
        self.valid_domains = {d.id for d in config.domains.domains}

    def route(self, metadata: dict[str, Any]) -> str:
        """Determine target domain for content.

        Routing precedence:
        1. Explicit domain in metadata (if valid)
        2. Source path matching routing rules
        3. Configured fallback domain

        Args:
            metadata: Content metadata (must include 'source_path')

        Returns:
            Domain ID to route content to
        """
        # Check for explicit domain override in frontmatter
        if "domain" in metadata:
            domain = cast(str, metadata["domain"])
            # Only use if it's a valid domain
            if domain in self.valid_domains:
                return domain

        # Check source_path against routing rules
        source_path = metadata.get("source_path", "")
        for rule in self.routing.source_rules:
            if rule.match in source_path:
                return rule.default_domain

        # Fall back to configured fallback domain
        return self.routing.fallback_domain

    def validate_domain(self, domain: str) -> bool:
        """Check if a domain ID is valid.

        Args:
            domain: Domain ID to validate

        Returns:
            True if domain exists in configuration
        """
        return domain in self.valid_domains

    def get_domain_for_source_path(self, source_path: str) -> str:
        """Get domain based on source path matching.

        This applies only routing rules, without checking for
        explicit domain overrides.

        Args:
            source_path: Path to source file

        Returns:
            Domain ID (from rules or fallback)
        """
        for rule in self.routing.source_rules:
            if rule.match in source_path:
                return rule.default_domain

        return self.routing.fallback_domain
