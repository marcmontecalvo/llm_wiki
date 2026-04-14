"""Domain model and registry."""

from typing import ClassVar

from llm_wiki.models.config import DomainConfig


class Domain:
    """Represents a wiki domain with its configuration and metadata."""

    def __init__(self, config: DomainConfig):
        """Initialize a domain from configuration.

        Args:
            config: Domain configuration
        """
        self.id = config.id
        self.title = config.title
        self.description = config.description
        self.owners = config.owners
        self.promote_to_shared = config.promote_to_shared

    def __repr__(self) -> str:
        """Return string representation."""
        return f"Domain(id={self.id!r}, title={self.title!r})"

    def __eq__(self, other: object) -> bool:
        """Check equality based on domain ID."""
        if not isinstance(other, Domain):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        """Return hash based on domain ID."""
        return hash(self.id)


class DomainRegistry:
    """Registry for managing wiki domains.

    Singleton pattern - only one registry instance per application.
    """

    _instance: ClassVar["DomainRegistry | None"] = None

    def __init__(self):
        """Initialize empty domain registry.

        Note: Use DomainRegistry.get_instance() or DomainRegistry.initialize()
        instead of calling this directly.
        """
        self._domains: dict[str, Domain] = {}

    @classmethod
    def get_instance(cls) -> "DomainRegistry":
        """Get the singleton domain registry instance.

        Returns:
            The domain registry instance

        Raises:
            RuntimeError: If registry has not been initialized
        """
        if cls._instance is None:
            raise RuntimeError(
                "DomainRegistry not initialized. Call DomainRegistry.initialize() first."
            )
        return cls._instance

    @classmethod
    def initialize(cls, domain_configs: list[DomainConfig]) -> "DomainRegistry":
        """Initialize the domain registry with configurations.

        Args:
            domain_configs: List of domain configurations

        Returns:
            The initialized registry instance
        """
        if cls._instance is None:
            cls._instance = cls()
        cls._instance._load_domains(domain_configs)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None

    def _load_domains(self, domain_configs: list[DomainConfig]) -> None:
        """Load domains from configuration.

        Args:
            domain_configs: List of domain configurations
        """
        self._domains.clear()
        for config in domain_configs:
            domain = Domain(config)
            self._domains[domain.id] = domain

    def get(self, domain_id: str) -> Domain | None:
        """Get a domain by ID.

        Args:
            domain_id: Domain identifier

        Returns:
            Domain if found, None otherwise
        """
        return self._domains.get(domain_id)

    def get_or_raise(self, domain_id: str) -> Domain:
        """Get a domain by ID, raising if not found.

        Args:
            domain_id: Domain identifier

        Returns:
            Domain instance

        Raises:
            KeyError: If domain not found
        """
        domain = self.get(domain_id)
        if domain is None:
            raise KeyError(f"Domain not found: {domain_id}")
        return domain

    def exists(self, domain_id: str) -> bool:
        """Check if a domain exists.

        Args:
            domain_id: Domain identifier

        Returns:
            True if domain exists, False otherwise
        """
        return domain_id in self._domains

    def list_all(self) -> list[Domain]:
        """Get all registered domains.

        Returns:
            List of all domains
        """
        return list(self._domains.values())

    def list_ids(self) -> list[str]:
        """Get all domain IDs.

        Returns:
            List of domain IDs
        """
        return list(self._domains.keys())

    def count(self) -> int:
        """Get the number of registered domains.

        Returns:
            Number of domains
        """
        return len(self._domains)

    def get_promotable_domains(self) -> list[Domain]:
        """Get domains that allow promotion to shared space.

        Returns:
            List of domains with promote_to_shared=True
        """
        return [d for d in self._domains.values() if d.promote_to_shared]
