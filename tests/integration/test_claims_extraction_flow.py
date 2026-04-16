"""Integration tests for claims extraction flow."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from llm_wiki.extraction.claims import ClaimsExtractor
from llm_wiki.extraction.enrichment import PageEnricher
from llm_wiki.index.metadata import MetadataIndex
from llm_wiki.utils.frontmatter import parse_frontmatter


class TestClaimsExtractionFlow:
    """Integration tests for end-to-end claims extraction and indexing."""

    @pytest.fixture
    def temp_wiki_dir(self):
        """Create temporary wiki directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_base = Path(tmpdir) / "wiki_system"
            wiki_base.mkdir()

            domain_dir = wiki_base / "domains" / "test_domain"
            queue_dir = domain_dir / "queue"
            pages_dir = domain_dir / "pages"
            queue_dir.mkdir(parents=True, exist_ok=True)
            pages_dir.mkdir(parents=True, exist_ok=True)
            (wiki_base / "index").mkdir()

            yield {
                "wiki_base": wiki_base,
                "domain": "test_domain",
                "queue_dir": queue_dir,
                "pages_dir": pages_dir,
                "tmpdir": Path(tmpdir),
            }

    @pytest.fixture
    def mock_client(self):
        """Create mock LLM client returning claims JSON."""
        client = Mock()
        client.chat_completion.return_value = json.dumps(
            {
                "claims": [
                    {
                        "claim": "Python was first released in 1991",
                        "confidence": 0.95,
                        "source_reference": "paragraph 1",
                        "temporal_context": "initial release",
                        "qualifiers": [],
                    },
                    {
                        "claim": "Python is an interpreted language",
                        "confidence": 0.9,
                        "source_reference": "section 1",
                        "temporal_context": None,
                        "qualifiers": ["generally"],
                    },
                ]
            }
        )
        return client

    def test_claims_written_to_frontmatter(self, temp_wiki_dir, mock_client):
        """Test that extracted claims are written to page frontmatter."""
        page_path = temp_wiki_dir["queue_dir"] / "python.md"
        page_path.write_text(
            "---\ntitle: Python\nid: python\nkind: entity\n---\n\nPython is a language.",
            encoding="utf-8",
        )

        extractor = ClaimsExtractor(client=mock_client)
        enricher = PageEnricher()

        metadata = {"title": "Python", "id": "python", "kind": "entity"}
        body = "Python is a language."
        extracted_claims = extractor.extract_claims(body, metadata, page_id="python")

        claims_dicts = [
            {
                "text": c.claim,
                "source_ref": c.source_reference,
                "confidence": c.confidence,
                "page_id": "python",
                "temporal_context": c.temporal_context,
                "qualifiers": c.qualifiers,
            }
            for c in extracted_claims
        ]

        enricher.enrich_page(page_path, metadata, claims=claims_dicts)

        content = page_path.read_text(encoding="utf-8")
        saved_metadata, _ = parse_frontmatter(content)

        assert "claims" in saved_metadata
        assert len(saved_metadata["claims"]) == 2
        claim_texts = [c["text"] for c in saved_metadata["claims"]]
        assert "Python was first released in 1991" in claim_texts
        assert "Python is an interpreted language" in claim_texts

    def test_claims_indexed_in_metadata_index(self, temp_wiki_dir, mock_client):
        """Test that claims are indexed and searchable in MetadataIndex."""
        index = MetadataIndex(index_dir=temp_wiki_dir["wiki_base"] / "index")

        metadata = {
            "id": "python",
            "title": "Python",
            "kind": "entity",
            "domain": "test_domain",
            "tags": ["python"],
            "claims": [
                {
                    "text": "Python was first released in 1991",
                    "source_ref": "paragraph 1",
                    "confidence": 0.95,
                    "page_id": "python",
                    "temporal_context": "initial release",
                    "qualifiers": [],
                },
                {
                    "text": "Python is an interpreted language",
                    "source_ref": "section 1",
                    "confidence": 0.9,
                    "page_id": "python",
                    "temporal_context": None,
                    "qualifiers": ["generally"],
                },
            ],
        }
        index.add_page("python", metadata)

        results = index.search_claims("Python")
        assert len(results) == 2
        # Results should be sorted by confidence descending
        assert results[0]["confidence"] >= results[1]["confidence"]

        results_1991 = index.search_claims("1991")
        assert len(results_1991) == 1
        assert results_1991[0]["text"] == "Python was first released in 1991"

    def test_claims_search_respects_min_confidence(self, temp_wiki_dir):
        """Test that search_claims filters by minimum confidence."""
        index = MetadataIndex(index_dir=temp_wiki_dir["wiki_base"] / "index")

        metadata = {
            "id": "page1",
            "title": "Page 1",
            "kind": "page",
            "domain": "test_domain",
            "tags": [],
            "claims": [
                {
                    "text": "High confidence fact",
                    "source_ref": "section 1",
                    "confidence": 0.9,
                    "page_id": "page1",
                },
                {
                    "text": "Low confidence fact",
                    "source_ref": "section 2",
                    "confidence": 0.3,
                    "page_id": "page1",
                },
            ],
        }
        index.add_page("page1", metadata)

        high_only = index.search_claims("fact", min_confidence=0.7)
        assert len(high_only) == 1
        assert high_only[0]["text"] == "High confidence fact"

        all_results = index.search_claims("fact", min_confidence=0.0)
        assert len(all_results) == 2

    def test_claims_persist_save_load(self, temp_wiki_dir):
        """Test that claims survive a save/load cycle."""
        index_dir = temp_wiki_dir["wiki_base"] / "index"
        index = MetadataIndex(index_dir=index_dir)

        metadata = {
            "id": "page1",
            "title": "Page 1",
            "kind": "page",
            "domain": "test_domain",
            "tags": [],
            "claims": [
                {
                    "text": "Persistent claim",
                    "source_ref": "section 1",
                    "confidence": 0.85,
                    "page_id": "page1",
                }
            ],
        }
        index.add_page("page1", metadata)
        index.save()

        index2 = MetadataIndex(index_dir=index_dir)
        index2.load()

        results = index2.search_claims("Persistent")
        assert len(results) == 1
        assert results[0]["text"] == "Persistent claim"
        assert results[0]["confidence"] == 0.85

    def test_get_claims_for_page(self, temp_wiki_dir):
        """Test getting all claims for a specific page."""
        index = MetadataIndex(index_dir=temp_wiki_dir["wiki_base"] / "index")

        for page_id, claim_text in [
            ("page1", "Claim from page one"),
            ("page2", "Claim from page two"),
        ]:
            index.add_page(
                page_id,
                {
                    "id": page_id,
                    "title": f"Page {page_id[-1]}",
                    "kind": "page",
                    "domain": "test_domain",
                    "tags": [],
                    "claims": [
                        {
                            "text": claim_text,
                            "source_ref": "section 1",
                            "confidence": 0.8,
                            "page_id": page_id,
                        }
                    ],
                },
            )

        page1_claims = index.get_claims_for_page("page1")
        assert len(page1_claims) == 1
        assert page1_claims[0]["text"] == "Claim from page one"

        page2_claims = index.get_claims_for_page("page2")
        assert len(page2_claims) == 1
        assert page2_claims[0]["text"] == "Claim from page two"

    def test_remove_page_clears_claims(self, temp_wiki_dir):
        """Test that removing a page also removes its claims from the index."""
        index = MetadataIndex(index_dir=temp_wiki_dir["wiki_base"] / "index")

        metadata = {
            "id": "page1",
            "title": "Page 1",
            "kind": "page",
            "domain": "test_domain",
            "tags": [],
            "claims": [
                {
                    "text": "A claim to be removed",
                    "source_ref": "section 1",
                    "confidence": 0.8,
                    "page_id": "page1",
                }
            ],
        }
        index.add_page("page1", metadata)
        assert len(index.get_claims_for_page("page1")) == 1

        index.remove_page("page1")
        assert len(index.get_claims_for_page("page1")) == 0
        assert index.search_claims("claim") == []

    def test_enricher_accepts_claims_parameter(self, temp_wiki_dir):
        """Test PageEnricher passes claims through to frontmatter without other extractions."""
        page_path = temp_wiki_dir["pages_dir"] / "test-page.md"
        page_path.write_text(
            "---\ntitle: Test\nid: test-page\n---\n\nSome content.",
            encoding="utf-8",
        )

        enricher = PageEnricher()
        extracted_meta = {"kind": "page", "summary": "A test page", "tags": []}
        claims = [
            {
                "text": "Test pages exist",
                "source_ref": "section 1",
                "confidence": 0.75,
                "page_id": "test-page",
            }
        ]

        enricher.enrich_page(page_path, extracted_meta, claims=claims)

        content = page_path.read_text(encoding="utf-8")
        saved_meta, _ = parse_frontmatter(content)

        assert "claims" in saved_meta
        assert saved_meta["claims"][0]["text"] == "Test pages exist"
        assert saved_meta["claims"][0]["confidence"] == 0.75
        # Other extractions should not be present
        assert "entities" not in saved_meta
        assert "concepts" not in saved_meta
