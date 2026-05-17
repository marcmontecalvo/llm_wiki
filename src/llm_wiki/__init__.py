"""Federated LLM wiki system with daemon governance."""

__version__ = "0.1.0"
__author__ = "Marc Montecalvo"
__description__ = "Federated LLM wiki system with daemon governance"

__all__ = [
    # Public API
    "Wiki",
    # Models
    "PageFrontmatter",
    "EntityFrontmatter",
    "ConceptFrontmatter",
    "SourceFrontmatter",
    "QAFrontmatter",
    "create_frontmatter",
    "DomainConfig",
    "WikiConfig",
    "DaemonConfig",
    "ModelProviderConfig",
    # Search
    "WikiQuery",
    # Model client
    "ModelClient",
    "OpenAICompatibleClient",
    "ClaudeAgentSDKClient",
    "create_model_client",
    "ModelClientError",
    # Adapters
    "SourceAdapter",
    "MarkdownAdapter",
    "TextAdapter",
    "ObsidianVaultAdapter",
    # Indexes
    "FulltextIndex",
    "MetadataIndex",
    "BacklinkIndex",
    "GraphEdgeIndex",
    # Governance
    "ClaimsExtractor",
    "ContentExtractor",
    "ContradictionDetector",
    "DuplicateDetector",
    "MetadataLinter",
    "QualityScorer",
    "RoutingMistakeDetector",
    "StalenessDetector",
    # Integration
    "DeterministicIntegrator",
    # Promotion
    "PromotionEngine",
    "PromotionCandidate",
    "PromotionScorer",
    # Review
    "ReviewQueue",
    # Misc
    "AdapterRegistry",
    "Claim",
    "ClaimExtraction",
    "DaemonConfig",
    # Config validation
    "ValidationError",
    "ValidationReport",
    "validate_config",
    # Daemon errors
    "DaemonError",
    "ConfigError",
    "SchedulerError",
    "SchedulerAlreadyRunningError",
    "JobNotFoundError",
    "WorkerPoolError",
    "WorkerPoolAlreadyStartedError",
    "WorkerPoolNotStartedError",
    # Daemon
    "WikiDaemon",
    "JobScheduler",
]

from pathlib import Path

from pydantic import BaseModel

from llm_wiki.adapters.base import SourceAdapter
from llm_wiki.adapters.markdown import MarkdownAdapter
from llm_wiki.adapters.obsidian import ObsidianVaultAdapter
from llm_wiki.adapters.text import TextAdapter
from llm_wiki.config.loader import load_config
from llm_wiki.config.validator import (
    ValidationError,
    ValidationReport,
    validate_config,
)
from llm_wiki.daemon.errors import (
    ConfigError,
    DaemonError,
    JobNotFoundError,
    SchedulerAlreadyRunningError,
    SchedulerError,
    WorkerPoolAlreadyStartedError,
    WorkerPoolError,
    WorkerPoolNotStartedError,
)
from llm_wiki.daemon.main import WikiDaemon
from llm_wiki.daemon.scheduler import JobScheduler
from llm_wiki.extraction.claims import ClaimsExtractor
from llm_wiki.extraction.service import ContentExtractor
from llm_wiki.governance.contradictions import ContradictionDetector
from llm_wiki.governance.duplicates import DuplicateDetector
from llm_wiki.governance.linter import MetadataLinter
from llm_wiki.governance.quality import QualityScorer
from llm_wiki.governance.routing_mistakes import RoutingMistakeDetector
from llm_wiki.governance.staleness import StalenessDetector
from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.index.fulltext import FulltextIndex
from llm_wiki.index.graph_edges import GraphEdgeIndex
from llm_wiki.index.metadata import MetadataIndex
from llm_wiki.integration.service import DeterministicIntegrator
from llm_wiki.models.client import (
    ClaudeAgentSDKClient,
    ModelClient,
    ModelClientError,
    OpenAICompatibleClient,
    create_model_client,
)
from llm_wiki.models.config import (
    DaemonConfig,
    DomainConfig,
    ModelProviderConfig,
    WikiConfig,
)
from llm_wiki.models.extraction import Claim, ClaimExtraction
from llm_wiki.models.page import (
    ConceptFrontmatter,
    EntityFrontmatter,
    PageFrontmatter,
    QAFrontmatter,
    SourceFrontmatter,
    create_frontmatter,
)
from llm_wiki.promotion.engine import PromotionEngine
from llm_wiki.promotion.models import PromotionCandidate
from llm_wiki.promotion.scorer import PromotionScorer
from llm_wiki.query.search import WikiQuery
from llm_wiki.review.queue import ReviewQueue


class Wiki(BaseModel):
    """High-level facade for the wiki library.

    This is the primary entry point for embedding LLM Wiki as a library
    in an agent harness. It provides a simple API over the daemon, search,
    and governance subsystems.

    Args:
        wiki_base: Path to the wiki base directory.
        config_dir: Path to configuration directory (defaults to wiki_base/config).

    Example:
        ```python
        from llm_wiki import Wiki

        wiki = Wiki("/path/to/wiki_system")
        results = wiki.search("artificial intelligence")
        wiki.ingest("/path/to/document.md")
        ```
    """

    wiki_base: Path
    config_dir: Path

    def model_post_init(self, __context: object) -> None:  # type: ignore[override]
        """Post-initialization: resolve config_dir default."""
        if self.config_dir == self.wiki_base:
            self.config_dir = self.wiki_base / "config"

    @classmethod
    def create(
        cls,
        wiki_base: str | Path,
        config_dir: str | Path | None = None,
    ) -> "Wiki":
        """Create a new Wiki instance.

        Args:
            wiki_base: Path to the wiki base directory.
            config_dir: Path to configuration directory.

        Returns:
            Wiki instance.
        """
        wiki_base = Path(wiki_base)
        if config_dir is None:
            config_dir = wiki_base / "config"
        return cls(wiki_base=wiki_base, config_dir=Path(config_dir))

    def search(
        self,
        query: str | None = None,
        domain: str | None = None,
        kind: str | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search wiki pages.

        Args:
            query: Fulltext search query.
            domain: Filter by domain.
            kind: Filter by page kind.
            tags: Filter by tags (AND).
            limit: Maximum results.

        Returns:
            List of matching pages with metadata.
        """
        indexer = WikiQuery(wiki_base=self.wiki_base)
        return indexer.search(query=query, domain=domain, kind=kind, tags=tags, limit=limit)

    def get_page(self, page_id: str) -> dict | None:
        """Get page metadata by ID.

        Args:
            page_id: Page identifier.

        Returns:
            Page metadata or None.
        """
        indexer = WikiQuery(wiki_base=self.wiki_base)
        return indexer.get_page(page_id)

    def get_backlinks(self, page_id: str) -> list[str]:
        """Get backlinks for a page.

        Args:
            page_id: Page identifier.

        Returns:
            List of page IDs that link to this page.
        """
        indexer = BacklinkIndex(index_dir=self.wiki_base / "index")
        indexer.load()
        return list(indexer.get_backlinks(page_id))

    def ingest(self, file_path: str | Path) -> dict:
        """Ingest a file into the wiki.

        Writes the file to the inbox directory for processing by the daemon's
        inbox scanner. The file is processed asynchronously.

        Args:
            file_path: Path to the file to ingest.

        Returns:
            Dict with ingestion status.
        """
        import shutil

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        inbox = self.wiki_base / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        dest = inbox / file_path.name
        shutil.copy2(file_path, dest)

        return {"status": "queued", "path": str(dest)}

    def get_domains(self) -> list[DomainConfig]:
        """Get configured domains.

        Returns:
            List of domain configurations.
        """
        try:
            config = load_config(self.config_dir)
            return config.domains.domains
        except Exception:
            return []

    @property
    def has_config(self) -> bool:
        """Check if configuration is present.

        Returns:
            True if config directory exists and is valid.
        """
        try:
            load_config(self.config_dir)
            return True
        except Exception:
            return False
