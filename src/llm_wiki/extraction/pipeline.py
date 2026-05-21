"""Extraction pipeline for processing queued pages."""

import logging
import re as _re_lib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from llm_wiki.models.extraction import ClaimExtraction
from llm_wiki.models.page import create_frontmatter
from llm_wiki.utils.frontmatter import parse_frontmatter, write_with_validation
from llm_wiki.utils.id_gen import generate_page_id

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    {
        "this",
        "that",
        "with",
        "from",
        "have",
        "will",
        "they",
        "been",
        "their",
        "there",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "these",
        "those",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "by",
        "can",
        "could",
        "did",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "further",
        "get",
        "got",
        "he",
        "her",
        "here",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "me",
        "might",
        "more",
        "most",
        "much",
        "must",
        "my",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "out",
        "over",
        "own",
        "s",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "the",
        "them",
        "then",
        "to",
        "together",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "why",
        "would",
        "you",
        "your",
    }
)


def _get_tags_heuristic(content: str, max_tags: int = 5) -> list[str]:
    """Return top N word frequencies, excluding stopwords.

    A simple TF-IDF approximation using word frequency without external libraries.
    """
    words = _re_lib.findall(r"\b[a-z]{4,}\b", content.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in _STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=lambda k: freq[k], reverse=True)[:max_tags]


def _get_summary_heuristic(content: str, max_chars: int = 200) -> str:
    """Return first non-heading paragraph, truncated to max_chars."""
    paras = _re_lib.split(r"\n\n+", content)
    for para in paras:
        stripped = para.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:max_chars]
    return content[:max_chars]


class ExtractionPipeline:
    """Pipeline for extracting and enriching wiki pages."""

    def __init__(
        self,
        wiki_base: Path | None = None,
        config_dir: Path | None = None,
        client: ModelClient | None = None,
        llm_extraction_enabled: bool = False,
    ):
        """Initialize extraction pipeline.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)
            config_dir: Config directory (defaults to config/)
            client: LLM client (if None and llm_extraction_enabled, creates from config)
            llm_extraction_enabled: When False, uses heuristic fallbacks for tags,
                summaries, and skips LLM-based extractors.
        """
        self.wiki_base = wiki_base or Path("wiki_system")
        self.config_dir = config_dir or Path("config")
        # Initialize LLM extractors when: explicit flag is True, OR when a
        # client is provided directly (e.g. in tests).  When both are False,
        # fall back to heuristics.
        self._llm_extraction_enabled = llm_extraction_enabled or client is not None

        if self._llm_extraction_enabled:
            if client is None:
                models_config = load_models_config(self.config_dir / "models.yaml")
                provider_config = models_config.get_provider("extraction")
                client = create_model_client(provider_config)

            self.content_extractor: ContentExtractor | None = ContentExtractor(
                client, self.config_dir
            )
            self.entity_extractor: EntityExtractor | None = EntityExtractor(client)
            self.concept_extractor: ConceptExtractor | None = ConceptExtractor(client)
            self.relationship_extractor: RelationshipExtractor | None = RelationshipExtractor(
                client
            )
            self.claims_extractor: ClaimsExtractor | None = ClaimsExtractor(client)
            self.qa_extractor: QAExtractor | None = QAExtractor(client)
        else:
            self.content_extractor = None
            self.entity_extractor = None
            self.concept_extractor = None
            self.relationship_extractor = None
            self.claims_extractor = None
            self.qa_extractor = None

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

        metadata, body = parse_frontmatter(content_text)

        # Extract metadata
        if self.content_extractor is not None:
            extracted_metadata = self.content_extractor.extract_metadata(filepath)
        else:
            # Minimal metadata when no content extractor — apply heuristic fallbacks
            extracted_metadata = {"kind": "page"}
            extracted_metadata["tags"] = _get_tags_heuristic(body)
            extracted_metadata["summary"] = _get_summary_heuristic(body)

        # Extract entities, concepts, and relationships
        entities = None
        concepts = None
        relationships = None

        page_kind = extracted_metadata.get("kind", "page")

        if self._llm_extraction_enabled:
            # Full LLM-based extraction
            assert self.entity_extractor is not None
            assert self.concept_extractor is not None
            assert self.relationship_extractor is not None
            assert self.claims_extractor is not None
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
            claim_extractions = self.claims_extractor.extract_claims(
                body, metadata, page_id=page_id
            )
            # Apply trust tags to LLM-extracted claims
            self._trust_tag_claims(claim_extractions, body)
            claims: list[dict[str, Any]] | None = None
            if claim_extractions:
                claims = [
                    {
                        "text": c.claim,
                        "source_ref": c.source_reference,
                        "confidence": c.confidence,
                        "page_id": page_id,
                        "trust_tag": c.trust_tag,
                        "temporal_context": c.temporal_context,
                        "qualifiers": c.qualifiers,
                    }
                    for c in claim_extractions
                ]
        else:
            # Heuristic fallback path — use page_id from metadata for LLM steps
            page_id = metadata.get("id", filepath.stem)
            claims = self._heuristic_extract_claims(body, page_id)

            if page_kind == "entity":
                entities = []
                relationships = []
            elif page_kind == "concept":
                concepts = []
                relationships = []

        # Extract relationships from the content (always, for both LLM and heuristic paths)
        if self._llm_extraction_enabled:
            assert self.relationship_extractor is not None
            relationships = self.relationship_extractor.extract_relationships_with_context(
                body, metadata, entities
            )
            if relationships:
                extracted_metadata["relationships"] = relationships
                logger.info(f"Extracted {len(relationships)} relationships from {filepath.name}")
        else:
            relationships = []

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
        if page_kind in ("page", "source") and self.qa_extractor is not None:
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
        if self.qa_extractor is None:
            return

        try:
            pairs = self.qa_extractor.extract_qa_pairs(parent_body, parent_metadata)
        except Exception as e:
            logger.warning(f"Q&A extraction failed for {parent_page_id}: {e}")
            return

        if not pairs:
            return

        now = datetime.now(UTC)
        parent_sources = parent_metadata.get("sources", []) or []

        for pair in pairs:
            question = pair["question"]
            answer = pair["answer"]
            tags = pair.get("tags", [])

            # QA pairs are converted into claim dicts with trust tags.
            # Question = extracted (direct user utterance).
            # Answer = inferred (derivation from the conversation).
            qa_claims = [
                {
                    "text": question,
                    "source_ref": "qa_question",
                    "confidence": 1.0,
                    "page_id": parent_page_id,
                    "trust_tag": "extracted",
                },
                {
                    "text": answer,
                    "source_ref": "qa_answer_derivation",
                    "confidence": 0.7,
                    "page_id": parent_page_id,
                    "trust_tag": "inferred",
                },
            ]

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
                claims=qa_claims,
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

    # ── Trust-tag helpers ───────────────────────────────────────────────────

    def _trust_tag_claims(self, claims: list[ClaimExtraction], body: str) -> list[ClaimExtraction]:
        """Mutate ``trust_tag`` on each ``ClaimExtraction`` in-place.

        Returns the same list (mutated) for ergonomic chaining.
        """
        from llm_wiki.ingest.trust_tag import classify_claim_provenance

        for ce in claims:
            ce.trust_tag = classify_claim_provenance(body, ce.claim, ce.source_reference)
        return claims

    # ── Heuristic claim extraction ──────────────────────────────────────────

    def _heuristic_extract_claims(self, content: str, page_id: str) -> list[dict[str, Any]]:
        """Split content into sentences and produce ``ClaimExtraction`` dicts.

        Used when LLM extraction is disabled.  Each sentence becomes a claim
        tagged via the deterministic heuristic.
        """
        from llm_wiki.ingest.trust_tag import classify_claim_provenance

        # Split on sentence-level boundaries (. ! ?) that end a paragraph.
        blocks = _re_lib.split(r"(?<=[.!?])\s+", content)
        claim_extractions: list[ClaimExtraction] = []
        for block in blocks:
            text = block.strip()
            if not text:
                continue
            # Skip markdown headings and very short bare list markers.
            if text.startswith("#"):
                continue
            if text.startswith("- ") and len(text) < 50:
                # Loose list marker or metadata — skip; longer bullets
                # may contain substantive content worth extracting.
                continue
            if len(text.split()) < 3:
                continue
            ce = ClaimExtraction(
                claim=text,
                source_reference="heuristic split",
                confidence=0.7,
            )
            ce.trust_tag = classify_claim_provenance(content, text, "heuristic split")
            claim_extractions.append(ce)

        # Cap claim count to avoid bloated frontmatter on long pages.
        max_claims = 20
        extracted = [
            {
                "text": c.claim,
                "source_ref": c.source_reference,
                "confidence": c.confidence,
                "page_id": page_id,
                "trust_tag": c.trust_tag,
                "temporal_context": c.temporal_context,
                "qualifiers": c.qualifiers,
            }
            for c in claim_extractions[:max_claims]
        ]
        if len(claim_extractions) > max_claims:
            logger.warning(
                "Trimmed %d heuristic claims to %d for page %s (page may be long)",
                len(claim_extractions),
                max_claims,
                page_id,
            )
        return extracted
