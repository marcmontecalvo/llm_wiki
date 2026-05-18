"""Tests for the FeaturesConfig model and feature flag system."""

import pytest
from pydantic import ValidationError

from llm_wiki.extraction.pipeline import (
    _get_summary_heuristic,
    _get_tags_heuristic,
)
from llm_wiki.models.config import FeaturesConfig


class TestFeaturesConfig:
    """Tests for FeaturesConfig schema."""

    def test_default_flags(self):
        """All feature flags default to False."""
        cfg = FeaturesConfig()
        assert cfg.llm_extraction is False
        assert cfg.synthesis_cache is False
        assert cfg.cross_domain_promotion is False

    def test_enable_llm_extraction(self):
        """Can enable llm_extraction."""
        cfg = FeaturesConfig(llm_extraction=True)
        assert cfg.llm_extraction is True

    def test_rejects_unknown_flags(self):
        """Unknown flags are rejected at startup."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            FeaturesConfig(unknown_flag=True)  # noqa: FBT003

    def test_rejects_multiple_unknown_flags(self):
        """Multiple unknown flags are rejected."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            FeaturesConfig(fake_flag=True, bogus=True)  # noqa: FBT003

    def test_enable_all_flags(self):
        """All flags can be set to True."""
        cfg = FeaturesConfig(
            llm_extraction=True,
            synthesis_cache=True,
            cross_domain_promotion=True,
        )
        assert all([cfg.llm_extraction, cfg.synthesis_cache, cfg.cross_domain_promotion])


class TestHeuristicFallback:
    """Tests for heuristic tag and summary extraction functions."""

    def test_get_tags_heuristic_basic(self):
        """Heuristic returns top words by frequency."""
        content = (
            "The quick brown fox jumps over the lazy dog. the fox is quick and the dog is lazy."
        )
        tags = _get_tags_heuristic(content, max_tags=3)
        assert len(tags) <= 3
        # "quick" appears twice, "fox" appears twice, "lazy" appears twice
        assert "quick" in tags or "fox" in tags or "lazy" in tags

    def test_get_tags_heuristic_empty(self):
        """Empty content returns empty list."""
        assert _get_tags_heuristic("") == []

    def test_get_tags_heuristic_stopwords_filtered(self):
        """Stopwords (>= 4 chars) are excluded from tags."""
        content = "this is with from they been their there which while who whom"
        tags = _get_tags_heuristic(content)
        # All words >= 4 chars are stopwords, so result should be empty
        assert tags == []

    def test_get_summary_heuristic_basic(self):
        """Returns first non-heading paragraph."""
        content = "# Title\n\nThis is the first paragraph.\n\nSecond paragraph here."
        summary = _get_summary_heuristic(content)
        assert "first paragraph" in summary

    def test_get_summary_heuristic_truncation(self):
        """Respects max_chars limit."""
        content = "This is a short paragraph."
        summary = _get_summary_heuristic(content, max_chars=10)
        assert len(summary) <= 10

    def test_get_summary_heuristic_no_headings(self):
        """Returns first paragraph when no headings exist."""
        content = "Just a plain paragraph.\n\nAnother one."
        summary = _get_summary_heuristic(content)
        assert "plain paragraph" in summary
