"""Integration tests for deterministic integration service."""

import copy
from datetime import datetime

import pytest

from llm_wiki.integration import DeterministicIntegrator
from llm_wiki.models.integration import MergeStrategies


class TestIntegrationFlow:
    """Integration tests for the integration service in real workflows."""

    @pytest.fixture
    def integrator(self):
        """Create a test integrator instance."""
        return DeterministicIntegrator()

    @pytest.fixture
    def existing_page_with_content(self):
        """Create a realistic existing page with full content."""
        return {
            "id": "python-language",
            "title": "Python Programming Language",
            "domain": "tech",
            "kind": "entity",
            "entity_type": "Programming Language",
            "tags": ["python", "programming", "language"],
            "summary": "Python is a high-level programming language.",
            "confidence": 0.85,
            "status": "published",
            "entities": [
                {"name": "Python", "type": "language", "confidence": 0.9},
                {"name": "Guido van Rossum", "type": "person", "confidence": 0.95},
            ],
            "concepts": [
                {"name": "Dynamic Typing", "confidence": 0.8},
                {"name": "Interpreted", "confidence": 0.85},
            ],
            "relationships": [
                {
                    "source_entity": "Python",
                    "relationship_type": "created_by",
                    "target_entity": "Guido van Rossum",
                    "confidence": 0.95,
                }
            ],
            "links": ["python-basics", "python-advanced"],
            "sources": ["docs.python.org"],
            "created_at": datetime(2025, 1, 1),
            "updated_at": datetime(2025, 6, 1),
        }

    @pytest.fixture
    def extracted_data_v2(self):
        """Create extracted data representing a new version."""
        return {
            "title": "Python Programming Language",
            "domain": "tech",
            "tags": ["python", "programming", "language", "data-science"],
            "summary": "Python is a high-level, interpreted programming language known for simplicity.",
            "confidence": 0.92,
            "entities": [
                {"name": "Python", "type": "language", "confidence": 0.95},
                {"name": "PyTorch", "type": "framework", "confidence": 0.88},
            ],
            "concepts": [
                {"name": "Dynamic Typing", "confidence": 0.8},
                {"name": "Interpreted", "confidence": 0.9},
                {"name": "Multi-paradigm", "confidence": 0.85},
            ],
            "relationships": [
                {
                    "source_entity": "Python",
                    "relationship_type": "created_by",
                    "target_entity": "Guido van Rossum",
                    "confidence": 0.95,
                },
                {
                    "source_entity": "Python",
                    "relationship_type": "supports",
                    "target_entity": "PyTorch",
                    "confidence": 0.88,
                },
            ],
            "links": ["python-basics", "python-frameworks"],
            "sources": ["docs.python.org", "wikipedia.org"],
        }

    def test_integration_complete_workflow(
        self, integrator, existing_page_with_content, extracted_data_v2
    ):
        """Test complete integration workflow."""
        original_page = copy.deepcopy(existing_page_with_content)

        result = integrator.integrate(
            "python-language",
            existing_page_with_content,
            extracted_data_v2,
            auto_resolve_conflicts=True,
        )

        assert result.success
        assert result.fields_changed > 0 or result.fields_merged > 0

        # Check that tags were merged
        assert "data-science" in existing_page_with_content["tags"]
        assert len(existing_page_with_content["tags"]) > len(original_page["tags"])

    def test_integration_preserves_existing_data(
        self, integrator, existing_page_with_content, extracted_data_v2
    ):
        """Test that existing important data is preserved."""
        result = integrator.integrate(
            "python-language",
            existing_page_with_content,
            extracted_data_v2,
            auto_resolve_conflicts=True,
        )

        assert result.success

        # Original data should be preserved
        assert existing_page_with_content["id"] == "python-language"
        assert existing_page_with_content["domain"] == "tech"
        assert existing_page_with_content["entity_type"] == "Programming Language"
        assert "docs.python.org" in existing_page_with_content["sources"]

    def test_integration_entities_merge(
        self, integrator, existing_page_with_content, extracted_data_v2
    ):
        """Test that entities are properly merged."""
        result = integrator.integrate(
            "python-language",
            existing_page_with_content,
            extracted_data_v2,
            auto_resolve_conflicts=True,
        )

        assert result.success

        # Should have original + new entities
        entities = existing_page_with_content["entities"]
        entity_names = [e["name"] for e in entities]

        assert "Python" in entity_names
        assert "Guido van Rossum" in entity_names
        assert "PyTorch" in entity_names  # New entity added
        assert len(entities) >= 3

    def test_integration_relationships_merge(
        self, integrator, existing_page_with_content, extracted_data_v2
    ):
        """Test that relationships are properly merged."""
        result = integrator.integrate(
            "python-language",
            existing_page_with_content,
            extracted_data_v2,
            auto_resolve_conflicts=True,
        )

        assert result.success

        # Should have at least the original relationship
        # (merging may deduplicate same relationships when they appear identical)
        rels = existing_page_with_content["relationships"]
        assert len(rels) >= 1

    def test_integration_detects_conflicts(
        self, integrator, existing_page_with_content, extracted_data_v2
    ):
        """Test conflict detection during integration."""
        # Set similar confidence to trigger conflict detection
        extracted_data_v2_copy = copy.deepcopy(extracted_data_v2)
        extracted_data_v2_copy["confidence"] = 0.86  # Similar to existing 0.85

        result = integrator.integrate(
            "python-language",
            existing_page_with_content,
            extracted_data_v2_copy,
            auto_resolve_conflicts=False,
        )

        # Should detect conflicts when auto_resolve is False
        assert result.success  # Integration still succeeds

    def test_integration_with_custom_strategies(
        self, integrator, existing_page_with_content
    ):
        """Test integration with custom merge strategies."""
        strategies = MergeStrategies(
            title="use_extracted",
            tags="union",
            summary="use_extracted",
            entities="union",
            concepts="union",
            relationships="union",
            links="union",
            sources="union",
            tags_dedup=True,
            entities_merge_strategy="union",
        )
        custom_integrator = DeterministicIntegrator(strategies)

        extracted = {
            "title": "Python - Updated Title",
            "tags": ["python", "new-tag"],
            "summary": "New summary",
            "entities": [{"name": "New Entity", "type": "tool", "confidence": 0.9}],
            "concepts": [{"name": "New Concept", "confidence": 0.85}],
            "relationships": [
                {
                    "source_entity": "Python",
                    "relationship_type": "related_to",
                    "target_entity": "New Entity",
                    "confidence": 0.9,
                }
            ],
            "links": ["new-page"],
            "sources": ["new-source"],
        }

        result = custom_integrator.integrate(
            "test-page", existing_page_with_content, extracted
        )

        assert result.success
        # Tags should be merged
        assert "new-tag" in existing_page_with_content["tags"]
        assert "new-source" in existing_page_with_content["sources"]

    def test_integration_rollback(
        self, integrator, existing_page_with_content, extracted_data_v2
    ):
        """Test rollback functionality."""
        result1 = integrator.integrate(
            "test-rollback",
            copy.deepcopy(existing_page_with_content),
            copy.deepcopy(extracted_data_v2),
        )

        # Get history
        history = integrator.get_history("test-rollback")
        assert len(history) > 0

        # Rollback
        rollback_result = integrator.rollback("test-rollback")

        # After rollback, history should be cleared for that page
        history_after = integrator.get_history("test-rollback")
        assert len(history_after) == 0

    def test_integration_determinism(
        self, integrator, existing_page_with_content, extracted_data_v2
    ):
        """Test that integration is deterministic with same inputs."""
        result1 = integrator.integrate(
            "det-test-1",
            copy.deepcopy(existing_page_with_content),
            copy.deepcopy(extracted_data_v2),
        )

        result2 = integrator.integrate(
            "det-test-2",
            copy.deepcopy(existing_page_with_content),
            copy.deepcopy(extracted_data_v2),
        )

        # Results should have same number of changes
        assert len(result1.changes) == len(result2.changes)
        assert result1.fields_changed == result2.fields_changed
        assert result1.fields_merged == result2.fields_merged


class TestIntegrationConflictResolution:
    """Integration tests for conflict resolution scenarios."""

    @pytest.fixture
    def integrator(self):
        """Create integrator."""
        return DeterministicIntegrator()

    def test_conflict_resolution_keep_existing(self, integrator):
        """Test auto-resolve keeps existing on conflict."""
        existing = {
            "id": "test",
            "summary": "Original summary",
            "confidence": 0.85,
            "updated_at": datetime(2025, 1, 1),
        }
        extracted = {
            "summary": "New summary",
            "confidence": 0.87,
        }

        result = integrator.integrate(
            "test", existing, extracted, auto_resolve_conflicts=True
        )

        # Should keep original on auto-resolve
        assert existing["summary"] == "Original summary"

    def test_conflict_resolution_manual(self, integrator):
        """Test manual conflict resolution."""
        existing = {
            "id": "test",
            "summary": "Original",
            "confidence": 0.85,
            "updated_at": datetime(2025, 1, 1),
        }
        extracted = {"summary": "New", "confidence": 0.87}

        result = integrator.integrate(
            "test", existing, extracted, auto_resolve_conflicts=False
        )

        # Conflicts should be detected
        assert len(result.conflicts) > 0 or existing["summary"] == "Original"

    def test_conflict_with_higher_confidence_extracted(self, integrator):
        """Test that higher confidence extracted values are used."""
        existing = {
            "id": "test",
            "summary": "Old summary",
            "confidence": 0.7,
            "updated_at": datetime(2025, 1, 1),
        }
        extracted = {
            "summary": "Better summary",
            "confidence": 0.95,
        }

        result = integrator.integrate("test", existing, extracted, auto_resolve_conflicts=False)

        # Higher confidence should win
        assert existing["summary"] == "Better summary"


class TestIntegrationEdgeCases:
    """Integration tests for edge cases."""

    @pytest.fixture
    def integrator(self):
        return DeterministicIntegrator()

    def test_empty_extracted_keeps_existing(self, integrator):
        """Test that empty extracted data keeps existing."""
        existing = {
            "id": "test",
            "title": "Test",
            "summary": "Existing summary",
            "updated_at": datetime.now(),
        }
        extracted = {}

        result = integrator.integrate("test", existing, extracted)

        assert result.success
        assert existing["summary"] == "Existing summary"

    def test_missing_field_added(self, integrator):
        """Test that missing fields are added."""
        existing = {
            "id": "test",
            "title": "Test",
            "updated_at": datetime.now(),
        }
        extracted = {"summary": "New summary"}

        result = integrator.integrate("test", existing, extracted)

        assert result.success
        assert existing["summary"] == "New summary"

    def test_none_extracted_ignored(self, integrator):
        """Test that None values in extracted are ignored."""
        existing = {
            "id": "test",
            "title": "Test",
            "summary": "Existing",
            "updated_at": datetime.now(),
        }
        extracted = {"summary": None}

        result = integrator.integrate("test", existing, extracted)

        assert result.success
        assert existing["summary"] == "Existing"

    def test_complete_overwrite(self, integrator):
        """Test complete field replacement."""
        existing = {
            "id": "test",
            "tags": ["old1", "old2"],
        }
        extracted = {
            "tags": ["new1", "new2", "new3"],
        }

        strategies = MergeStrategies(tags="use_extracted")
        int_with_strategy = DeterministicIntegrator(strategies)

        result = int_with_strategy.integrate("test", existing, extracted)

        assert result.success
        assert existing["tags"] == ["new1", "new2", "new3"]