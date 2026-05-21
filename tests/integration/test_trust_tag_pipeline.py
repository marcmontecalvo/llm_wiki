"""Integration tests for trust-tagged claim flow through the extraction pipeline."""

from pathlib import Path
from textwrap import dedent

import pytest

from llm_wiki.extraction.pipeline import ExtractionPipeline


@pytest.fixture
def wiki_tmp(tmp_path: Path) -> Path:
    """Minimal wiki structure with one domain queue."""
    wiki = tmp_path / "wiki"
    domain = wiki / "domains" / "gen" / "queue"
    domain.mkdir(parents=True)
    # Empty index dir
    (tmp_path / "wiki" / "index").mkdir(parents=True)
    return wiki


_fixture_content = dedent("""\
    ---
    id: test-doc
    kind: source
    title: Test Document
    domain: gen
    ---
    Machine learning models improve with more training data.
    The system may experience latency under heavy load.
    Therefore, investment in infrastructure is critical.
    Rust is a systems programming language for safety.
    OK
    """)


class TestPipelineTrustTags:
    """Integration tests verifying trust tags flow through the heuristic path."""

    def test_heuristic_path_produces_claims_with_trust_tags(self, wiki_tmp: Path):
        """Heuristic path must produce claim dicts with trust_tag field."""
        src = wiki_tmp / "domains" / "gen" / "queue" / "test.md"
        src.write_text(_fixture_content, encoding="utf-8")

        pipeline = ExtractionPipeline(wiki_base=wiki_tmp, llm_extraction_enabled=False)
        stats = pipeline.process_queue("gen")

        assert stats["processed"] == 1, "Should have processed one file"

        # Verify claims were written to the active page
        active_pages = (wiki_tmp / "domains" / "gen" / "pages").glob("*.md")
        active = list(active_pages)
        assert len(active) == 1, f"Expected 1 page in pages/, got {len(active)}"

        content = active[0].read_text(encoding="utf-8")
        import frontmatter as fm

        post = fm.loads(content)
        metadata = post.metadata

        # Claims must be in frontmatter with trust_tags
        assert "claims" in metadata, "Claims must be present in frontmatter"
        claims = metadata["claims"]
        assert len(claims) >= 1, "Must produce at least one claim"

        for c in claims:
            assert "trust_tag" in c, f"Each claim must have trust_tag: {c}"
            assert c["trust_tag"] in {"extracted", "inferred", "ambiguous"}

    def test_verbatim_claims_are_extracted(self, wiki_tmp: Path):
        """A verbatim sentence should get trust_tag=extracted."""
        content = dedent("""\
            ---
            id: verbatim-test
            kind: source
            title: Verbatim
            domain: gen
            ---
            The conference will be held in June.
            It may be postponed.
            """)
        src = wiki_tmp / "domains" / "gen" / "queue" / "verbatim.md"
        src.write_text(content, encoding="utf-8")

        wiki = wiki_tmp
        (wiki_tmp / "wiki_tmp2" / "wiki" / "index").mkdir(parents=True, exist_ok=True)
        # Use a separate tmp_path
        wiki = wiki_tmp / "wiki2"
        domain = wiki / "domains" / "gen" / "queue"
        domain.mkdir(parents=True)
        (wiki / "index").mkdir(parents=True)

        src2 = domain / "verbatim2.md"
        src2.write_text(content, encoding="utf-8")

        pipeline = ExtractionPipeline(wiki_base=wiki, llm_extraction_enabled=False)
        stats = pipeline.process_queue("gen")

        assert stats["processed"] == 1

        pages = (wiki / "domains" / "gen" / "pages").glob("*.md")
        page_files = list(pages)
        assert page_files

        import frontmatter as fm

        post = fm.loads(page_files[0].read_text(encoding="utf-8"))
        claims = post.metadata.get("claims", [])
        tags = [c["trust_tag"] for c in claims]
        assert "extracted" in tags, "Must have at least one extracted claim"
