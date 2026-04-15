"""Extraction pipeline for processing queued pages."""

import logging
import shutil
from pathlib import Path

from llm_wiki.extraction.concepts import ConceptExtractor
from llm_wiki.extraction.enrichment import PageEnricher
from llm_wiki.extraction.entities import EntityExtractor
from llm_wiki.extraction.relationships import RelationshipExtractor
from llm_wiki.extraction.service import ContentExtractor
from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.models.client import ModelClient, create_model_client
from llm_wiki.models.config import load_models_config

logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """Pipeline for extracting and enriching wiki pages."""

    def __init__(
        self,
        wiki_base: Path | None = None,
        config_dir: Path | None = None,
        client: ModelClient | None = None,
    ):
        """Initialize extraction pipeline.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            config_dir: Config directory (defaults to config/)
            client: LLM client (if None, creates from config)
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.config_dir = config_dir or Path("config")

        # Initialize LLM client
        if client is None:
            models_config = load_models_config(self.config_dir / "models.yaml")
            provider_config = models_config.get_provider("extraction")
            client = create_model_client(provider_config)

        # Initialize extractors
        self.content_extractor = ContentExtractor(client, self.config_dir)
        self.entity_extractor = EntityExtractor(client)
        self.concept_extractor = ConceptExtractor(client)
        self.relationship_extractor = RelationshipExtractor(client)
        self.enricher = PageEnricher()

        # Initialize backlink index
        self.backlinks = BacklinkIndex(index_dir=self.wiki_base / "index")
        self.backlinks.load()

    def process_queue(self, domain: str) -> dict[str, int]:
        """Process all files in a domain's queue.

        Args:
            domain: Domain ID to process

        Returns:
            Statistics dictionary (processed, failed, skipped)
        """
        stats = {"processed": 0, "failed": 0, "skipped": 0}

        queue_dir = self.wiki_base / "domains" / domain / "queue"
        if not queue_dir.exists():
            logger.warning(f"Queue directory not found: {queue_dir}")
            return stats

        # Get all markdown files in queue
        files = list(queue_dir.glob("*.md"))
        logger.info(f"Processing {len(files)} file(s) from {domain} queue")

        for filepath in files:
            try:
                self._process_file(filepath, domain)
                stats["processed"] += 1
            except Exception as e:
                logger.error(f"Failed to process {filepath.name}: {e}")
                stats["failed"] += 1

        return stats

    def _process_file(self, filepath: Path, domain: str) -> None:
        """Process a single queued file.

        Args:
            filepath: Path to queued file
            domain: Domain ID

        Raises:
            Exception: If processing fails
        """
        logger.info(f"Processing {filepath.name}")

        # Read file content for extraction
        content_text = filepath.read_text(encoding="utf-8")
        from llm_wiki.utils.frontmatter import parse_frontmatter

        metadata, body = parse_frontmatter(content_text)

        # Extract metadata
        extracted_metadata = self.content_extractor.extract_metadata(filepath)

        # Extract entities, concepts, and relationships (only for entity/concept pages)
        entities = None
        concepts = None
        relationships = None

        page_kind = extracted_metadata.get("kind", "page")
        if page_kind == "entity":
            entities = self.entity_extractor.extract_entities(body, metadata)
            relationships = self.relationship_extractor.extract_relationships_with_context(
                body, metadata, entities
            )
        elif page_kind == "concept":
            concepts = self.concept_extractor.extract_concepts(body, metadata)
            relationships = self.relationship_extractor.extract_relationships(body, metadata)

        # Enrich the page
        self.enricher.enrich_page(filepath, extracted_metadata, entities, concepts, relationships)

        # Move to active wiki
        active_dir = self.wiki_base / "domains" / domain / "pages"
        active_dir.mkdir(parents=True, exist_ok=True)

        target_path = active_dir / filepath.name
        shutil.move(str(filepath), str(target_path))

        logger.info(f"Moved {filepath.name} to {domain}/pages/")

        # Update backlink index
        page_id = metadata.get("id", filepath.stem)
        self.backlinks.add_page_links(page_id, body)
        self.backlinks.save()

    def process_all_queues(self) -> dict[str, dict[str, int]]:
        """Process all domain queues.

        Returns:
            Statistics by domain
        """
        domains_dir = self.wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return {}

        results = {}
        for domain_dir in domains_dir.iterdir():
            if domain_dir.is_dir():
                domain_id = domain_dir.name
                stats = self.process_queue(domain_id)
                results[domain_id] = stats

        return results
