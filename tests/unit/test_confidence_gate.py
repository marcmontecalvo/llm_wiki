"""Tests for confidence gating (Story 2.2)."""

from __future__ import annotations

from pathlib import Path

from llm_wiki.governance.confidence_gate import check_confidence_gate


class TestConfidenceGate:
    """Tests for the confidence gate checker."""

    def test_passes_when_above_threshold(self, temp_dir: Path):
        """A high-quality page (source + updated) passes the gate."""
        page = temp_dir / "good.md"
        page.write_text(
            "---\nid: good\ntitle: Good Page\nsource: http://example.com\n"
            "created: 2025-01-01T00:00:00Z\nupdated: 2025-02-01T00:00:00Z\n---\n"
            "# Content\n\nSubstantial content here with good structure.\n\n- Point 1\n- Point 2\n"
        )
        result = check_confidence_gate(page, threshold=0.3)

        assert result.passed
        assert result.score > 0.3
        assert result.reason is None

    def test_fails_when_below_threshold(self, temp_dir: Path):
        """A page without a source and never updated drops below threshold."""
        page = temp_dir / "low.md"
        page.write_text(
            "---\nid: low\ntitle: Low Quality\ncreated: 2025-01-01T00:00:00Z\n"
            "updated: 2025-01-01T00:00:00Z\n---\nShort content\n"
        )
        result = check_confidence_gate(page, threshold=0.3)

        assert not result.passed
        assert result.reason is not None
        assert "below threshold" in result.reason

    def test_default_threshold(self, temp_dir: Path):
        """With the default 0.3 threshold, a minimal page passes via trust neutral."""
        page = temp_dir / "neutral.md"
        page.write_text(
            "---\nid: neutral\ntitle: Neutral\nsource: http://example.com\n"
            "created: 2025-01-01T00:00:00Z\nupdated: 2025-02-01T00:00:00Z\n---\n"
            "# Happy Content\n\nEverything looks fine here.\n"
        )
        result = check_confidence_gate(page)

        assert result.passed

    def test_custom_threshold(self, temp_dir: Path):
        """Raise the threshold to 0.8 — same page fails."""
        page = temp_dir / "good.md"
        page.write_text(
            "---\nid: good\ntitle: Good Page\nsource: http://example.com\n"
            "created: 2025-01-01T00:00:00Z\nupdated: 2025-02-01T00:00:00Z\n---\n"
            "# Content\n\nSubstantial content here with good structure.\n\n- Point 1\n- Point 2\n"
        )
        result = check_confidence_gate(page, threshold=0.9)

        assert not result.passed

    def test_ambiguous_claims_reduce_score(self, temp_dir: Path):
        """Page with ambiguous claims scores lower than claimed page."""
        ambiguous_page = temp_dir / "ambiguous.md"
        ambiguous_page.write_text(
            "---\nid: ambiguous\ntitle: Ambiguous Claims\n"
            "source: http://example.com\n"
            "created: 2025-01-01T00:00:00Z\nupdated: 2025-02-01T00:00:00Z\n"
            "claims:\n  - text: 'Maybe true'\n    trust_tag: ambiguous\n---\n# Content\n\nText.\n"
        )
        claimed_page = temp_dir / "claimed.md"
        claimed_page.write_text(
            "---\nid: claimed\ntitle: Clear Claims\n"
            "source: http://example.com\n"
            "created: 2025-01-01T00:00:00Z\nupdated: 2025-02-01T00:00:00Z\n"
            "claims:\n  - text: 'Facts are listed here'\n    trust_tag: extracted\n---\n# Content\n\nText.\n"
        )
        result = check_confidence_gate(ambiguous_page)
        claimed_result = check_confidence_gate(claimed_page)

        # Ambiguous.reduce confidence relative to extracted claims
        assert claimed_result.score > result.score
