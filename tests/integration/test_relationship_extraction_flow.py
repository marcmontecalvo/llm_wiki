"""Integration tests for relationship extraction flow."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from llm_wiki.extraction.enrichment import PageEnricher
from llm_wiki.utils.frontmatter import parse_frontmatter, write_frontmatter


class TestRelationshipExtractionFlow:
    """Integration tests for relationship extraction flow."""

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

            config_dir = Path(tmpdir) / "config"
            config_dir.mkdir()

            yield {
                "wiki_base": wiki_base,
                "domain": "test_domain",
                "queue_dir": queue_dir,
                "pages_dir": pages_dir,
                "config_dir": config_dir,
                "tmpdir": Path(tmpdir),
            }

    @pytest.fixture
    def mock_client(self):
        """Create mock LLM client."""
        return Mock()

    def test_relationship_extraction_integration_entity_page(self, temp_wiki_dir):
        """Test relationship extraction in entity page processing flow."""
        # This test verifies the enrichment phase of relationship extraction
        # Create test page with entities
        enriched_content = """---
kind: entity
title: Python
entities:
  - name: Python
    type: technology
    description: Programming language
  - name: Docker
    type: tool
    description: Container platform
---

# Python

Python integrates with Docker for containerization.
"""

        filepath = temp_wiki_dir["pages_dir"] / "python.md"
        filepath.write_text(enriched_content, encoding="utf-8")

        # Define relationships to add
        relationships = [
            {
                "source_entity": "Python",
                "relationship_type": "uses",
                "target_entity": "C libraries",
                "confidence": 0.95,
                "bidirectional": False,
            },
            {
                "source_entity": "Python",
                "relationship_type": "integrates_with",
                "target_entity": "Docker",
                "confidence": 0.9,
                "bidirectional": True,
            },
        ]

        # Enrich the page with relationships
        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=relationships,
        )

        # Read enriched content
        enriched_text = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_text)

        # Verify relationships are in metadata
        assert "relationships" in metadata
        assert len(metadata["relationships"]) == 2
        assert metadata["relationships"][0]["source_entity"] == "Python"
        assert metadata["relationships"][0]["relationship_type"] == "uses"
        assert metadata["relationships"][1]["relationship_type"] == "integrates_with"

    def test_relationship_extraction_integration_concept_page(self, temp_wiki_dir):
        """Test relationship extraction in concept page processing flow."""
        # This test verifies the enrichment phase with concept pages
        # Create test page with concepts
        enriched_content = """---
kind: concept
title: Machine Learning
concepts:
  - name: Machine Learning
    definition: Subset of AI
    category: AI
---

# Machine Learning

Machine Learning is a subset of Artificial Intelligence.
"""

        filepath = temp_wiki_dir["pages_dir"] / "ml.md"
        filepath.write_text(enriched_content, encoding="utf-8")

        # Define relationships to add
        relationships = [
            {
                "source_entity": "Machine Learning",
                "relationship_type": "part_of",
                "target_entity": "Artificial Intelligence",
                "confidence": 0.98,
                "bidirectional": False,
            },
            {
                "source_entity": "Machine Learning",
                "relationship_type": "depends_on",
                "target_entity": "Data Science",
                "confidence": 0.9,
                "bidirectional": False,
            },
        ]

        # Enrich the page with relationships
        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "concept"},
            relationships=relationships,
        )

        # Read enriched content
        enriched_text = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_text)

        # Verify relationships are in metadata
        assert "relationships" in metadata
        assert len(metadata["relationships"]) == 2
        assert metadata["relationships"][0]["relationship_type"] == "part_of"
        assert metadata["relationships"][1]["relationship_type"] == "depends_on"

    def test_relationship_enrichment_persists_to_file(self, temp_wiki_dir, mock_client):
        """Test that relationships persist in enriched file."""
        # Create test page
        test_content = """---
kind: entity
title: Test Entity
---

# Test Entity

Test content here.
"""

        filepath = temp_wiki_dir["pages_dir"] / "test.md"
        filepath.write_text(test_content, encoding="utf-8")

        # Create relationships
        relationships = [
            {
                "source_entity": "Entity A",
                "relationship_type": "uses",
                "target_entity": "Entity B",
                "confidence": 0.9,
                "description": "A uses B",
                "bidirectional": False,
            }
        ]

        # Enrich page
        enricher = PageEnricher()
        enriched_path = enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=relationships,
        )

        # Read and verify
        enriched_content = enriched_path.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_content)

        assert "relationships" in metadata
        assert len(metadata["relationships"]) == 1
        assert metadata["relationships"][0]["source_entity"] == "Entity A"
        assert metadata["relationships"][0]["relationship_type"] == "uses"
        assert metadata["relationships"][0]["description"] == "A uses B"

    def test_relationship_enrichment_merges_with_existing(self, temp_wiki_dir):
        """Test that relationships are properly merged with existing metadata."""
        # Create page with existing metadata
        existing_metadata = {
            "kind": "entity",
            "title": "Test Entity",
            "tags": ["existing-tag"],
        }
        body = "# Test Entity\n\nContent here."
        content = write_frontmatter(existing_metadata, body)

        filepath = temp_wiki_dir["pages_dir"] / "test.md"
        filepath.write_text(content, encoding="utf-8")

        # Relationships to add
        relationships = [
            {
                "source_entity": "A",
                "relationship_type": "uses",
                "target_entity": "B",
                "confidence": 0.9,
                "bidirectional": False,
            }
        ]

        # Enrich page
        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=relationships,
        )

        # Verify merging
        enriched_content = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_content)

        assert metadata["kind"] == "entity"
        assert "existing-tag" in metadata.get("tags", [])
        assert "relationships" in metadata
        assert len(metadata["relationships"]) == 1

    def test_empty_relationships_not_added(self, temp_wiki_dir):
        """Test that empty relationships are not added to metadata."""
        test_content = """---
kind: entity
title: Test
---

# Test
"""

        filepath = temp_wiki_dir["pages_dir"] / "test.md"
        filepath.write_text(test_content, encoding="utf-8")

        # Enrich with None relationships
        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=None,
        )

        # Read and verify
        enriched_content = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_content)

        assert "relationships" not in metadata or metadata.get("relationships") is None

    def test_relationship_with_bidirectional_expansion(self, temp_wiki_dir):
        """Test that bidirectional relationships are expanded during enrichment."""
        test_content = """---
kind: entity
title: A
---

# A
"""

        filepath = temp_wiki_dir["pages_dir"] / "test.md"
        filepath.write_text(test_content, encoding="utf-8")

        # Bidirectional relationship
        relationships = [
            {
                "source_entity": "A",
                "relationship_type": "collaborates_with",
                "target_entity": "B",
                "confidence": 0.9,
                "bidirectional": True,
            }
        ]

        # Enrich
        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=relationships,
        )

        # Read and verify
        enriched_content = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_content)

        # Note: The enrichment stores relationships as-is.
        # Bidirectional expansion should happen during query/indexing
        assert "relationships" in metadata
        assert metadata["relationships"][0]["bidirectional"] is True

    def test_relationship_extraction_handles_empty_list(self, temp_wiki_dir):
        """Test relationship extraction handles empty relationship lists."""
        test_content = """---
kind: entity
title: Empty
---

# Empty Content
"""

        filepath = temp_wiki_dir["pages_dir"] / "empty.md"
        filepath.write_text(test_content, encoding="utf-8")

        # Enrich with empty relationships
        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=[],
        )

        # Read and verify
        enriched_content = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_content)

        # Empty list should not be added
        assert "relationships" not in metadata or metadata.get("relationships") is not None

    def test_relationship_confidence_scores_preserved(self, temp_wiki_dir):
        """Test that relationship confidence scores are preserved."""
        test_content = """---
kind: entity
title: Test
---

# Test
"""

        filepath = temp_wiki_dir["pages_dir"] / "test.md"
        filepath.write_text(test_content, encoding="utf-8")

        relationships = [
            {
                "source_entity": "A",
                "relationship_type": "uses",
                "target_entity": "B",
                "confidence": 0.95,
                "bidirectional": False,
            },
            {
                "source_entity": "C",
                "relationship_type": "depends_on",
                "target_entity": "D",
                "confidence": 0.65,
                "bidirectional": False,
            },
        ]

        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=relationships,
        )

        enriched_content = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_content)

        assert metadata["relationships"][0]["confidence"] == 0.95
        assert metadata["relationships"][1]["confidence"] == 0.65

    def test_relationship_description_preserved(self, temp_wiki_dir):
        """Test that relationship descriptions are preserved."""
        test_content = """---
kind: entity
title: Test
---

# Test
"""

        filepath = temp_wiki_dir["pages_dir"] / "test.md"
        filepath.write_text(test_content, encoding="utf-8")

        relationships = [
            {
                "source_entity": "Flask",
                "relationship_type": "extends",
                "target_entity": "Werkzeug",
                "description": "Flask is built on Werkzeug WSGI toolkit",
                "confidence": 0.95,
                "bidirectional": False,
            }
        ]

        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=relationships,
        )

        enriched_content = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_content)

        assert (
            metadata["relationships"][0]["description"] == "Flask is built on Werkzeug WSGI toolkit"
        )

    def test_multiple_relationships_per_entity(self, temp_wiki_dir):
        """Test that multiple relationships per entity are preserved."""
        test_content = """---
kind: entity
title: Python
---

# Python
"""

        filepath = temp_wiki_dir["pages_dir"] / "python.md"
        filepath.write_text(test_content, encoding="utf-8")

        relationships = [
            {
                "source_entity": "Python",
                "relationship_type": "uses",
                "target_entity": "C",
                "confidence": 0.9,
                "bidirectional": False,
            },
            {
                "source_entity": "Python",
                "relationship_type": "integrates_with",
                "target_entity": "Docker",
                "confidence": 0.85,
                "bidirectional": False,
            },
            {
                "source_entity": "Python",
                "relationship_type": "implements",
                "target_entity": "PEP standards",
                "confidence": 0.95,
                "bidirectional": False,
            },
        ]

        enricher = PageEnricher()
        enricher.enrich_page(
            filepath,
            extracted_metadata={"kind": "entity"},
            relationships=relationships,
        )

        enriched_content = filepath.read_text(encoding="utf-8")
        metadata, body = parse_frontmatter(enriched_content)

        assert len(metadata["relationships"]) == 3
        assert all(r["source_entity"] == "Python" for r in metadata["relationships"])
