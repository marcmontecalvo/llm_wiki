"""Tests for src/llm_wiki/ingest/trust_tag.py."""

from llm_wiki.ingest import trust_tag


class TestClassifyClaimProvenance:
    """Tests for classify_claim_provenance."""

    def test_verbatim_extracted(self):
        """Claim appearing verbatim in source must be 'extracted'."""
        src = "Rust is a systems programming language designed for safety and performance."
        assert (
            trust_tag.classify_claim_provenance(
                src, "Rust is a systems programming language designed for safety and performance."
            )
            == "extracted"
        )

    def test_case_insensitive_extracted(self):
        """Minor casing differences should match as extracted."""
        src = "Rust was first released in 2015."
        claim = "rust was first released in 2015"
        assert trust_tag.classify_claim_provenance(src, claim) == "extracted"

    def test_reasoning_word_not_in_source(self):
        """Reasoning word absent from source => inferred."""
        src = "Claude can generate JSON responses."
        assert (
            trust_tag.classify_claim_provenance(src, "Therefore, Claude is a useful tool.")
            == "inferred"
        )

    def test_does_not_imply_inferred_when_source_has_similar_word(self):
        """If reasoning word exists in source, fallback to default (inferred unless verbatim)."""
        src = "This implies that LLMs are improving."
        assert (
            trust_tag.classify_claim_provenance(src, "This implies that LLMs are improving.")
            == "extracted"
        )

    def test_hedge_language(self):
        """Hedging words should produce 'ambiguous'."""
        src = "The system may experience latency under heavy load."
        assert (
            trust_tag.classify_claim_provenance(src, "The system may experience latency")
            == "ambiguous"
        )

    def test_short_claim(self):
        """Claims under 15 chars are ambiguous."""
        assert trust_tag.classify_claim_provenance("some source text", "too short") == "ambiguous"

    def test_determinism(self):
        """Same inputs must always produce same output."""
        src = "Machine learning models improve with more training data."
        claim = "Machine learning models improve with more training data."
        results = [trust_tag.classify_claim_provenance(src, claim) for _ in range(100)]
        assert all(r == results[0] for r in results)

    def test_empty_claim(self):
        """Very short (empty-ish) claims are ambiguous."""
        assert trust_tag.classify_claim_provenance("some source", "  ") == "ambiguous"

    def test_qa_question_is_extracted(self):
        """A Q&A pair's question is the exact user utterance => extracted."""
        src = "Q: How do I configure domains?\nA: Set the domain ID."
        assert (
            trust_tag.classify_claim_provenance(src, "How do I configure domains?") == "extracted"
        )

    def test_derivation_inferred(self):
        """Derived conclusion not literally in source => inferred."""
        src = "The wiki uses a徵inment pipeline for ingestion."
        claim = "Consequently, the pipeline handles ingestion."
        assert trust_tag.classify_claim_provenance(src, claim) == "inferred"

    def test_multiple_hedge_words(self):
        """Multiple hedges still classify as ambiguous."""
        src = "Knowledge bases require maintenance."
        assert (
            trust_tag.classify_claim_provenance(src, "Perhaps maybe likely the system is good")
            == "ambiguous"
        )

    def test_suggests_not_in_source(self):
        """'suggests' not present in source => inferred."""
        src = "The vector index supports similarity search."
        assert (
            trust_tag.classify_claim_provenance(
                src, "This suggests that vector indexes are useful."
            )
            == "inferred"
        )

    def test_source_reference_does_not_affect_result(self):
        """source_reference is informational only."""
        src = "Pydantic provides data validation."
        assert (
            trust_tag.classify_claim_provenance(
                src, "Pydantic provides data validation.", "section 1"
            )
            == "extracted"
        )
        assert (
            trust_tag.classify_claim_provenance(src, "Pydantic provides data validation.", None)
            == "extracted"
        )
