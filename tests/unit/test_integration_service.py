"""Tests for deterministic integration service."""

import copy
from datetime import datetime

import pytest

from llm_wiki.integration import DeterministicIntegrator, IntegrationError
from llm_wiki.models.integration import (
    Change,
    IntegrationConflict,
    MergeStrategies,
)


class TestDeterministicIntegrator:
    """Tests for DeterministicIntegrator class."""

    @pytest.fixture
    def integrator(self):
        """Create a test integrator instance."""
        return DeterministicIntegrator()

    @pytest.fixture
    def existing_page(self):
        """Create a test existing page."""
        return {
            "id": "test-page-1",
            "title": "Python Programming",
            "domain": "programming",
            "tags": ["python", "programming"],
            "summary": "Guide to Python",
            "confidence": 0.8,
            "updated_at": datetime(2026, 1, 1),
            "created_at": datetime(2025, 1, 1),
            "links": ["page-2", "page-3"],
            "sources": ["source-1"],
        }

    @pytest.fixture
    def extracted_data(self):
        """Create test extracted data."""
        return {
            "tags": ["python", "coding", "scripting"],
            "summary": "Comprehensive guide to Python programming",
            "confidence": 0.95,
            "links": ["page-2", "page-4"],
            "sources": ["source-1", "source-2"],
        }

    def test_initialize_with_default_strategies(self):
        """Test initializing integrator with default strategies."""
        integrator = DeterministicIntegrator()
        assert integrator.strategies is not None
        assert integrator.strategies.title == "keep_existing"
        assert integrator.strategies.tags == "union"
        assert integrator.strategies.confidence == "prefer_newer"

    def test_initialize_with_custom_strategies(self):
        """Test initializing integrator with custom strategies."""
        strategies = MergeStrategies(title="use_extracted")
        integrator = DeterministicIntegrator(strategies)
        assert integrator.strategies.title == "use_extracted"

    def test_keep_existing_strategy(self, integrator, existing_page, extracted_data):
        """Test keep_existing strategy preserves existing value."""
        extracted_data.pop("tags")  # Remove tags to focus on title
        existing_page["title"] = "Original Title"
        extracted_data["title"] = "New Title"

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert existing_page["title"] == "Original Title"
        assert not any(c.field == "title" for c in result.changes)

    def test_use_extracted_strategy(self, integrator, existing_page, extracted_data):
        """Test use_extracted strategy replaces existing value."""
        strategies = MergeStrategies(summary="use_extracted")
        integrator = DeterministicIntegrator(strategies)

        original_summary = existing_page["summary"]
        new_summary = extracted_data["summary"]

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert existing_page["summary"] == new_summary
        assert existing_page["summary"] != original_summary
        assert any(c.field == "summary" and c.change_type == "updated" for c in result.changes)

    def test_union_strategy_tags(self, integrator, existing_page, extracted_data):
        """Test union strategy combines tags without duplicates."""
        existing_page["tags"] = ["python", "programming"]
        extracted_data["tags"] = ["python", "coding", "scripting"]

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert "python" in existing_page["tags"]
        assert "programming" in existing_page["tags"]
        assert "coding" in existing_page["tags"]
        assert "scripting" in existing_page["tags"]
        # Should not have duplicates
        assert len(existing_page["tags"]) == 4
        # Check change was recorded
        assert any(c.field == "tags" and c.change_type == "merged" for c in result.changes)

    def test_union_strategy_links(self, integrator, existing_page, extracted_data):
        """Test union strategy for links."""
        existing_page["links"] = ["page-2", "page-3"]
        extracted_data["links"] = ["page-2", "page-4"]

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert existing_page["links"] == ["page-2", "page-3", "page-4"]
        assert any(c.field == "links" and c.change_type == "merged" for c in result.changes)

    def test_union_strategy_sources(self, integrator, existing_page, extracted_data):
        """Test union strategy for sources."""
        existing_page["sources"] = ["source-1", "source-2"]
        extracted_data["sources"] = ["source-2", "source-3", "source-4"]

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert "source-1" in existing_page["sources"]
        assert "source-2" in existing_page["sources"]
        assert "source-3" in existing_page["sources"]
        assert "source-4" in existing_page["sources"]

    def test_prefer_newer_with_higher_confidence(self, integrator, existing_page, extracted_data):
        """Test prefer_newer strategy with higher confidence value."""
        existing_page["confidence"] = 0.8
        extracted_data["confidence"] = 0.95  # Higher confidence
        existing_page["summary"] = "Old summary"
        extracted_data["summary"] = "New summary with high confidence"

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert existing_page["summary"] == "New summary with high confidence"
        assert any(c.field == "summary" and c.change_type == "updated" for c in result.changes)

    def test_prefer_newer_with_similar_confidence_conflict(
        self, integrator, existing_page, extracted_data
    ):
        """Test prefer_newer strategy detects conflict with similar confidence."""
        strategies = MergeStrategies()
        integrator = DeterministicIntegrator(strategies)

        existing_page["confidence"] = 0.85
        extracted_data["confidence"] = 0.87  # Similar confidence
        existing_page["summary"] = "Old summary"
        extracted_data["summary"] = "Different summary"

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert len(result.conflicts) > 0
        assert any(c.field == "summary" for c in result.conflicts)

    def test_prefer_newer_auto_resolve_conflicts(self, integrator, existing_page, extracted_data):
        """Test prefer_newer with auto_resolve keeps existing on conflict."""
        strategies = MergeStrategies()
        integrator = DeterministicIntegrator(strategies)

        existing_page["confidence"] = 0.85
        extracted_data["confidence"] = 0.87
        original_summary = "Old summary"
        existing_page["summary"] = original_summary
        extracted_data["summary"] = "Different summary"

        result = integrator.integrate(
            "test-1", existing_page, extracted_data, auto_resolve_conflicts=True
        )

        assert result.success
        # When auto-resolving, should keep existing
        assert existing_page["summary"] == original_summary

    def test_added_field_strategy(self, integrator, existing_page, extracted_data):
        """Test adding new field that didn't exist."""
        # Remove confidence from existing
        del existing_page["confidence"]
        extracted_data["confidence"] = 0.95

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert existing_page["confidence"] == 0.95
        assert any(c.field == "confidence" and c.change_type == "added" for c in result.changes)

    def test_no_extracted_value_preserves_existing(self, integrator, existing_page):
        """Test that missing extracted value preserves existing."""
        extracted_data = {}  # No extracted data

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert existing_page["title"] == "Python Programming"

    def test_updated_timestamp_on_changes(self, integrator, existing_page, extracted_data):
        """Test that updated_at timestamp is set when changes occur."""
        original_timestamp = existing_page["updated_at"]
        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert existing_page["updated_at"] != original_timestamp
        assert any(c.field == "updated_at" for c in result.changes)

    def test_no_timestamp_update_without_changes(self, integrator, existing_page):
        """Test that timestamp is not updated when no changes occur."""
        extracted_data = {}  # No data to extract
        original_timestamp = existing_page["updated_at"]

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        # No changes means no timestamp update
        assert existing_page["updated_at"] == original_timestamp

    def test_integration_result_statistics(self, integrator, existing_page, extracted_data):
        """Test that integration result includes correct statistics."""
        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert result.total_fields_checked > 0
        assert result.fields_changed > 0
        assert result.fields_merged > 0
        assert result.has_changes()

    def test_integration_result_no_conflicts(self, integrator, existing_page, extracted_data):
        """Test result indicates no conflicts when none occur."""
        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert not result.has_conflicts()

    def test_integration_result_to_dict(self, integrator, existing_page, extracted_data):
        """Test converting result to dictionary."""
        result = integrator.integrate("test-1", existing_page, extracted_data)

        result_dict = result.to_dict()

        assert result_dict["page_id"] == "test-1"
        assert result_dict["success"]
        assert "changes" in result_dict
        assert "conflicts" in result_dict
        assert "statistics" in result_dict

    def test_change_to_dict(self):
        """Test converting Change to dictionary."""
        change = Change(
            field="tags",
            old_value=["a"],
            new_value=["a", "b"],
            change_type="merged",
            timestamp=datetime.now(),
            reason="Added new tag",
        )

        change_dict = change.to_dict()

        assert change_dict["field"] == "tags"
        assert change_dict["change_type"] == "merged"
        assert change_dict["reason"] == "Added new tag"

    def test_conflict_to_dict(self):
        """Test converting IntegrationConflict to dictionary."""
        conflict = IntegrationConflict(
            field="summary",
            existing_value="Old summary",
            extracted_value="New summary",
            resolution="manual_review",
            reason="Different values",
            confidence_diff=0.05,
        )

        conflict_dict = conflict.to_dict()

        assert conflict_dict["field"] == "summary"
        assert conflict_dict["resolution"] == "manual_review"
        assert conflict_dict["confidence_diff"] == 0.05

    def test_rollback_support(self, integrator, existing_page, extracted_data):
        """Test rollback support for integration history."""
        # First integration
        result1 = integrator.integrate("test-1", existing_page, extracted_data)
        assert result1.success

        # Get history
        history = integrator.get_history("test-1")
        assert len(history) == 1

        # Can rollback
        rollback_result = integrator.rollback("test-1", steps=1)
        assert rollback_result is not None
        assert rollback_result.success

    def test_rollback_nonexistent_page(self, integrator):
        """Test rollback on page with no history."""
        result = integrator.rollback("nonexistent-page")
        assert result is None

    def test_determinism_same_input_same_output(self, integrator):
        """Test that same input always produces same output (determinism)."""
        existing_page = {
            "id": "test",
            "title": "Test",
            "domain": "test",
            "tags": ["a", "b"],
            "confidence": 0.8,
            "updated_at": datetime(2026, 1, 1),
        }
        extracted_data = {"tags": ["b", "c"], "confidence": 0.9}

        # Run integration twice with identical input
        page1 = copy.deepcopy(existing_page)
        result1 = integrator.integrate("test-1", page1, copy.deepcopy(extracted_data))

        page2 = copy.deepcopy(existing_page)
        result2 = integrator.integrate("test-1", page2, copy.deepcopy(extracted_data))

        # Results should be identical (except timestamps which are non-deterministic)
        page1_no_ts = {k: v for k, v in page1.items() if k != "updated_at"}
        page2_no_ts = {k: v for k, v in page2.items() if k != "updated_at"}
        assert page1_no_ts == page2_no_ts
        assert len(result1.changes) == len(result2.changes)
        assert len(result1.conflicts) == len(result2.conflicts)

    def test_integration_with_complex_objects(self, integrator):
        """Test integration with complex nested objects."""
        existing_page = {
            "id": "test",
            "entities": [
                {"name": "Python", "type": "language", "confidence": 0.9},
                {"name": "Django", "type": "framework", "confidence": 0.85},
            ],
            "updated_at": datetime(2026, 1, 1),
        }
        extracted_data = {
            "entities": [
                {"name": "Python", "type": "language", "confidence": 0.95},
                {"name": "Flask", "type": "framework", "confidence": 0.88},
            ],
        }

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        # Should have 3 entities total (Python, Django, Flask)
        assert len(existing_page["entities"]) == 3

    def test_empty_extracted_data(self, integrator, existing_page):
        """Test integration with empty extracted data."""
        original_page = copy.deepcopy(existing_page)
        extracted_data = {}

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert existing_page == original_page
        assert not result.has_changes()

    def test_none_values_handled_correctly(self, integrator, existing_page):
        """Test that None values are handled correctly."""
        extracted_data = {
            "summary": None,
            "confidence": None,
        }

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        # None values should not override existing
        assert existing_page["summary"] == "Guide to Python"

    def test_multiple_fields_integration(self, integrator, existing_page, extracted_data):
        """Test integration across multiple fields simultaneously."""
        extracted_data["links"] = ["new-page"]
        extracted_data["sources"] = ["new-source"]

        result = integrator.integrate("test-1", existing_page, extracted_data)

        assert result.success
        assert result.fields_changed > 0
        # Check multiple fields were changed
        changed_fields = {c.field for c in result.changes}
        assert "links" in changed_fields or "sources" in changed_fields

    def test_clear_history(self, integrator, existing_page, extracted_data):
        """Test clearing integration history."""
        integrator.integrate("test-1", existing_page, extracted_data)
        assert len(integrator.get_history("test-1")) > 0

        integrator.clear_history("test-1")
        assert len(integrator.get_history("test-1")) == 0

    def test_clear_all_history(self, integrator, existing_page, extracted_data):
        """Test clearing all integration history."""
        integrator.integrate("test-1", copy.deepcopy(existing_page), copy.deepcopy(extracted_data))
        integrator.integrate("test-2", copy.deepcopy(existing_page), copy.deepcopy(extracted_data))

        integrator.clear_history()
        assert len(integrator.get_history("test-1")) == 0
        assert len(integrator.get_history("test-2")) == 0


class TestItemExists:
    """Tests for the _item_exists helper method."""

    def test_item_exists_simple_values(self):
        """Test finding simple values in list."""
        integrator = DeterministicIntegrator()
        items = ["a", "b", "c"]

        assert integrator._item_exists(items, "a")
        assert not integrator._item_exists(items, "d")

    def test_item_exists_dict_by_name(self):
        """Test finding dict items by name field."""
        integrator = DeterministicIntegrator()
        items = [
            {"name": "Python", "type": "language"},
            {"name": "Java", "type": "language"},
        ]

        assert integrator._item_exists(items, {"name": "Python", "version": "3.9"})
        assert not integrator._item_exists(items, {"name": "Go", "type": "language"})

    def test_item_exists_dict_by_claim(self):
        """Test finding dict items by claim field."""
        integrator = DeterministicIntegrator()
        items = [
            {"claim": "Python was created in 1991", "source": "src1"},
            {"claim": "Java was created in 1995", "source": "src2"},
        ]

        assert integrator._item_exists(
            items, {"claim": "Python was created in 1991", "confidence": 0.9}
        )
        assert not integrator._item_exists(items, {"claim": "Ruby was created in 1995"})

    def test_item_exists_dict_by_multiple_fields(self):
        """Test finding dict items using multiple identifying fields."""
        integrator = DeterministicIntegrator()
        items = [
            {
                "source_entity": "Python",
                "relationship_type": "created_by",
                "target_entity": "Guido",
            }
        ]

        # Should find by matching key fields
        assert integrator._item_exists(
            items,
            {
                "source_entity": "Python",
                "relationship_type": "created_by",
                "target_entity": "Guido",
                "confidence": 0.95,
            },
        )


class TestIntegrationErrors:
    """Tests for error handling."""

    def test_integration_error_on_failure(self):
        """Test that IntegrationError is raised on failure."""
        integrator = DeterministicIntegrator()

        # Cause an error by passing bad data
        with pytest.raises(IntegrationError):
            # This will fail during integration
            integrator.integrate("test", None, {})  # type: ignore

    def test_invalid_page_id(self):
        """Test handling of invalid page ID."""
        integrator = DeterministicIntegrator()

        # Should handle gracefully (page_id is just a string)
        result = integrator.integrate("", {"title": "Test"}, {})
        assert result.success  # Empty string is technically valid


class TestMergeStrategiesConfiguration:
    """Tests for merge strategies configuration."""

    def test_custom_merge_strategy_configuration(self):
        """Test creating custom merge strategy configuration."""
        strategies = MergeStrategies(
            title="use_extracted",
            tags="union",
            summary="prefer_newer",
        )

        assert strategies.title == "use_extracted"
        assert strategies.tags == "union"
        assert strategies.summary == "prefer_newer"
        # Others should use defaults
        assert strategies.domain == "keep_existing"

    def test_merge_strategies_model_serialization(self):
        """Test serializing merge strategies."""
        strategies = MergeStrategies(title="use_extracted")
        strategies_dict = strategies.model_dump()

        assert strategies_dict["title"] == "use_extracted"
        assert "tags" in strategies_dict
        assert "confidence" in strategies_dict
