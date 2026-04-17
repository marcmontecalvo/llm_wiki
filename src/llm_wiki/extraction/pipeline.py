"""Extraction pipeline for processing queued pages."""

import logging
import shutil
from pathlib import Path

from datetime import datetime, timezone

from llm_wiki.extraction.claims import ClaimsExtractor
from llm_wiki.extraction.concepts import ConceptExtractor
from llm_wiki.extraction.enrichment import PageEnricher
from llm_wiki.extraction.entities import EntityExtractor
from llm_wiki.extraction.qa import QAExtractor
from llm_wiki.extraction.relationships import RelationshipExtractor
from llm_wiki.extraction.service import ContentExtractor
from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.index.graph_edges import GraphEdgeIndex
from llm_wiki.models.client import ModelClient, create_model_client
from llm_wiki.models.config import load_models_config
from llm_wiki.models.page import create_frontmatter
from llm_wiki.utils.frontmatter import write_with_validation
from llm_wiki.utils.id_gen import generate_page_id

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
        self.claims_extractor = ClaimsExtractor(client)
        self.qa_extractor = QAExtractor(client)
        self.enricher = PageEnricher()

        # Initialize backlink index
        self.backlinks = BacklinkIndex(index_dir=self.wiki_base / "index")
        self.backlinks.load()

        # Initialize graph edge index
        self.graph_edges = GraphEdgeIndex(index_dir=self.wiki_base / "index")
        self.graph_edges.load()

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

        # Extract claims from all pages (not just entity/concept)
        page_id = metadata.get("id", filepath.stem)
        claim_extractions = self.claims_extractor.extract_claims(body, metadata, page_id=page_id)
        claims = None
        if claim_extractions:
            claims = [
                {
                    "text": c.claim,
                    "source_ref": c.source_reference,
                    "confidence": c.confidence,
                    "page_id": page_id,
                    "temporal_context": c.temporal_context,
                    "qualifiers": c.qualifiers,
                }
                for c in claim_extractions
            ]

        # Extract relationships from the content
        relationships = self.relationship_extractor.extract_relationships_with_context(
            body, metadata, entities
        )
        if relationships:
            extracted_metadata["relationships"] = relationships
            logger.info(f"Extracted {len(relationships)} relationships from {filepath.name}")

        # Enrich the page
        self.enricher.enrich_page(
            filepath, extracted_metadata, entities, concepts, relationships, claims
        )

        # Move to active wiki
        active_dir = self.wiki_base / "domains" / domain / "pages"
        active_dir.mkdir(parents=True, exist_ok=True)

        target_path = active_dir / filepath.name
        shutil.move(str(filepath), str(target_path))

        logger.info(f"Moved {filepath.name} to {domain}/pages/")

        # Materialize Q&A pages derived from this source/page. Skip kinds that
        # don't carry Q&A-shaped content (entity, concept, qa).
        if page_kind in ("page", "source"):
            self._emit_qa_pages(
                parent_page_id=page_id,
                parent_body=body,
                parent_metadata=metadata,
                domain=domain,
                active_dir=active_dir,
            )

        # Update backlink index
        page_id = metadata.get("id", filepath.stem)
        self.backlinks.add_page_links(page_id, body)
        self.backlinks.save()

        # Update graph edge index
        import re

        links = re.findall(r"\[\[([^\]]+)\]\]", body)
        self.graph_edges.update_page_links(page_id, links)
        if relationships:
            self.graph_edges.update_page_relationships(page_id, relationships)
        self.graph_edges.save()

    def _emit_qa_pages(
        self,
        parent_page_id: str,
        parent_body: str,
        parent_metadata: dict,
        domain: str,
        active_dir: Path,
    ) -> None:
        """Extract Q&A pairs and write each as its own ``kind: qa`` wiki page.

        Args:
            parent_page_id: ID of the source page the Q&A was extracted from.
            parent_body: Body content of the source page.
            parent_metadata: Parent frontmatter — used for domain, source refs.
            domain: Domain ID to write Q&A pages into.
            active_dir: Active pages directory for the domain.
        """
        try:
            pairs = self.qa_extractor.extract_qa_pairs(parent_body, parent_metadata)
        except Exception as e:
            logger.warning(f"Q&A extraction failed for {parent_page_id}: {e}")
            return

        if not pairs:
            return

        now = datetime.now(timezone.utc)
        parent_sources = parent_metadata.get("sources", []) or []

        for pair in pairs:
            question = pair["question"]
            answer = pair["answer"]
            tags = pair.get("tags", [])

            # Generate a collision-free id scoped to the domain pages dir.
            def _collision_check(candidate: str) -> bool:
                return (active_dir / f"{candidate}.md").exists()

            page_id = generate_page_id(
                title=f"qa {question}"[:80],
                domain=domain,
                collision_check=_collision_check,
            )

            frontmatter_obj = create_frontmatter(
                kind="qa",
                id=page_id,
                title=question[:120],
                domain=domain,
                question=question,
                answer=answer,
                tags=tags,
                related_pages=[parent_page_id],
                sources=parent_sources,
                updated_at=now,
                created_at=now,
                status="draft",
                confidence=0.6,
            )

            # Body mirrors the answer as readable markdown. Schema holds the
            # canonical fields; body is for humans reading the file directly.
            body = f"**Q:** {question}\n\n**A:** {answer}\n"
            content = write_with_validation(frontmatter_obj, body)

            out_path = active_dir / f"{page_id}.md"
            out_path.write_text(content, encoding="utf-8")

            # Index backlink from qa → parent source page.
            self.backlinks.add_page_links(page_id, f"[[{parent_page_id}]]")
            self.graph_edges.update_page_links(page_id, [parent_page_id])

            logger.info(f"Wrote Q&A page {page_id} (from {parent_page_id})")

        # Persist indices after batch.
        self.backlinks.save()
        self.graph_edges.save()

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
