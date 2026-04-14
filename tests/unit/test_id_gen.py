"""Tests for ID generation utilities."""

import pytest

from llm_wiki.utils.id_gen import (
    generate_concept_id,
    generate_entity_id,
    generate_page_id,
    slugify,
)


class TestSlugify:
    """Tests for slugify function."""

    def test_basic_slugify(self):
        """Test basic text to slug conversion."""
        assert slugify("Hello World") == "hello-world"
        assert slugify("Python Programming") == "python-programming"

    def test_special_characters(self):
        """Test handling of special characters."""
        assert slugify("Hello, World!") == "hello-world"
        assert slugify("Python 3.11+") == "python-3-11"
        assert slugify("C++ Programming") == "c-programming"
        assert slugify("Hello@#$%World") == "hello-world"

    def test_unicode_normalization(self):
        """Test unicode character normalization."""
        assert slugify("Über cool") == "uber-cool"
        assert slugify("Café") == "cafe"
        assert slugify("naïve") == "naive"

    def test_multiple_hyphens_collapsed(self):
        """Test multiple hyphens are collapsed to one."""
        assert slugify("Hello   World") == "hello-world"
        assert slugify("A -- B -- C") == "a-b-c"
        assert slugify("Test---Page") == "test-page"

    def test_leading_trailing_hyphens_removed(self):
        """Test leading/trailing hyphens are removed."""
        assert slugify("-Hello-") == "hello"
        assert slugify("--Test--") == "test"
        assert slugify(" -Start ") == "start"

    def test_max_length(self):
        """Test max length truncation."""
        long_text = "a" * 200
        result = slugify(long_text, max_length=50)
        assert len(result) == 50

    def test_max_length_no_trailing_hyphen(self):
        """Test truncation doesn't leave trailing hyphen."""
        text = "hello world this is a very long title"
        result = slugify(text, max_length=15)
        assert not result.endswith("-")
        assert len(result) <= 15

    def test_empty_string(self):
        """Test empty string returns empty slug."""
        assert slugify("") == ""
        assert slugify("   ") == ""
        assert slugify("!!!") == ""

    def test_numbers_preserved(self):
        """Test numbers are preserved in slugs."""
        assert slugify("Python 3.11") == "python-3-11"
        assert slugify("Version 2.0") == "version-2-0"
        assert slugify("123 Main Street") == "123-main-street"

    def test_lowercase_conversion(self):
        """Test all text is converted to lowercase."""
        assert slugify("HELLO") == "hello"
        assert slugify("HeLLo WoRLd") == "hello-world"
        assert slugify("PYTHON") == "python"


class TestGeneratePageId:
    """Tests for generate_page_id function."""

    def test_basic_id_generation(self):
        """Test basic ID generation from title."""
        assert generate_page_id("Machine Learning") == "machine-learning"
        assert generate_page_id("Python Programming") == "python-programming"

    def test_with_domain_prefix(self):
        """Test ID generation with domain prefix."""
        assert generate_page_id("Python", domain="general") == "general-python"
        assert generate_page_id("Docker", domain="homelab") == "homelab-docker"

    def test_collision_handling(self):
        """Test collision detection and counter."""
        existing_ids = {"test", "test-2", "test-3"}

        def collision_check(page_id: str) -> bool:
            return page_id in existing_ids

        result = generate_page_id("Test", collision_check=collision_check)
        assert result == "test-4"

    def test_collision_with_domain(self):
        """Test collision handling with domain prefix."""
        existing_ids = {"general-python", "general-python-2"}

        def collision_check(page_id: str) -> bool:
            return page_id in existing_ids

        result = generate_page_id("Python", domain="general", collision_check=collision_check)
        assert result == "general-python-3"

    def test_max_length_with_domain(self):
        """Test max length with domain prefix."""
        long_title = "A" * 100
        result = generate_page_id(long_title, domain="test", max_length=20)
        assert len(result) <= 20
        assert result.startswith("test-")

    def test_max_length_respects_collision_suffix(self):
        """Test max length accounts for collision suffix."""
        existing_ids = {"test"}

        def collision_check(page_id: str) -> bool:
            return page_id in existing_ids

        result = generate_page_id("Test", collision_check=collision_check, max_length=10)
        assert result == "test-2"
        assert len(result) <= 10

    def test_empty_title_raises(self):
        """Test empty title raises ValueError."""
        with pytest.raises(ValueError, match="Cannot generate ID"):
            generate_page_id("")

        with pytest.raises(ValueError, match="Cannot generate ID"):
            generate_page_id("!!!")

    def test_too_many_collisions_raises(self):
        """Test too many collisions raises ValueError."""

        def always_collides(page_id: str) -> bool:
            return True

        with pytest.raises(ValueError, match="Too many ID collisions"):
            generate_page_id("Test", collision_check=always_collides)

    def test_deterministic_generation(self):
        """Test ID generation is deterministic."""
        title = "Machine Learning Basics"
        id1 = generate_page_id(title)
        id2 = generate_page_id(title)
        assert id1 == id2

    def test_special_characters_in_title(self):
        """Test special characters are handled properly."""
        assert generate_page_id("C++ Programming") == "c-programming"
        assert generate_page_id("Hello, World!") == "hello-world"
        assert generate_page_id("Test@Example.com") == "test-example-com"

    def test_very_short_max_length_with_domain(self):
        """Test very short max_length falls back to no domain."""
        result = generate_page_id("Test Title", domain="verylongdomain", max_length=15)
        # Domain would take too much space, should use full slug
        assert result == "test-title"


class TestGenerateEntityId:
    """Tests for generate_entity_id function."""

    def test_basic_entity_id(self):
        """Test basic entity ID generation."""
        assert generate_entity_id("Apple Inc.") == "apple-inc"
        assert generate_entity_id("John Doe") == "john-doe"

    def test_with_entity_type(self):
        """Test entity ID with type prefix."""
        assert generate_entity_id("John Doe", entity_type="person") == "person-john-doe"
        assert generate_entity_id("Apple", entity_type="company") == "company-apple"

    def test_collision_handling(self):
        """Test entity ID collision handling."""
        existing_ids = {"john-doe"}

        def collision_check(entity_id: str) -> bool:
            return entity_id in existing_ids

        result = generate_entity_id("John Doe", collision_check=collision_check)
        assert result == "john-doe-2"

    def test_with_entity_type_and_collision(self):
        """Test entity ID with type and collision."""
        existing_ids = {"person-alice-smith"}

        def collision_check(entity_id: str) -> bool:
            return entity_id in existing_ids

        result = generate_entity_id(
            "Alice Smith", entity_type="person", collision_check=collision_check
        )
        assert result == "person-alice-smith-2"


class TestGenerateConceptId:
    """Tests for generate_concept_id function."""

    def test_basic_concept_id(self):
        """Test basic concept ID generation."""
        assert generate_concept_id("Machine Learning") == "machine-learning"
        assert generate_concept_id("Artificial Intelligence") == "artificial-intelligence"

    def test_collision_handling(self):
        """Test concept ID collision handling."""
        existing_ids = {"neural-networks"}

        def collision_check(concept_id: str) -> bool:
            return concept_id in existing_ids

        result = generate_concept_id("Neural Networks", collision_check=collision_check)
        assert result == "neural-networks-2"

    def test_max_length(self):
        """Test concept ID max length."""
        long_name = "A" * 200
        result = generate_concept_id(long_name, max_length=50)
        assert len(result) == 50


class TestIdGenerationConsistency:
    """Tests for consistency across ID generation functions."""

    def test_all_ids_url_safe(self):
        """Test all IDs are URL-safe."""
        test_cases = [
            generate_page_id("Test & Example"),
            generate_entity_id("Company, Inc."),
            generate_concept_id("Machine Learning (ML)"),
        ]

        for page_id in test_cases:
            # Should only contain lowercase letters, numbers, and hyphens
            assert page_id.islower() or page_id.replace("-", "").isalnum()
            assert " " not in page_id
            assert "." not in page_id
            assert "," not in page_id

    def test_no_leading_trailing_hyphens(self):
        """Test IDs don't have leading/trailing hyphens."""
        test_cases = [
            generate_page_id("-Test-"),
            generate_entity_id("--Company--"),
            generate_concept_id("---Concept---"),
        ]

        for page_id in test_cases:
            assert not page_id.startswith("-")
            assert not page_id.endswith("-")
