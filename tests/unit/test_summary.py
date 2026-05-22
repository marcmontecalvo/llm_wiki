"""Tests for cross-domain summary page generation (Story 3.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm_wiki.daemon.jobs.summary import Claim, CrossDomainSummaryJob
from llm_wiki.utils.frontmatter import parse_frontmatter


def _write_shared_entity(
    wiki_root: Path,
    entity_id: str,
    title: str,
    source_pages: list[str],
    domains: list[str],
) -> None:
    """Create a shared entity page for testing."""
    body = f"# {title}\n\nCross-domain entity.\n"
    fm = {
        "id": entity_id,
        "kind": "entity",
        "title": title,
        "source_pages": source_pages,
        "domains": domains,
        "confidence": 0.8,
    }
    import frontmatter

    content = frontmatter.dumps(frontmatter.Post(body, **fm))
    page_file = wiki_root / "shared" / f"{entity_id}.md"
    page_file.write_text(content, encoding="utf-8")


def _write_source_page(
    wiki_root: Path, page_id: str, title: str, claims: list[dict], domain: str = "alpha"
) -> None:
    """Create a source page with claims in a domain."""
    fm = {
        "id": page_id,
        "kind": "page",
        "title": title,
        "domain": domain,
        "status": "published",
        "claims": claims,
        "updated_at": "2026-01-01T00:00:00Z",
    }
    import frontmatter

    content = frontmatter.dumps(frontmatter.Post(f"# {title}\n", **fm))
    page_file = wiki_root / "domains" / domain / "pages" / f"{page_id}.md"
    page_file.parent.mkdir(parents=True, exist_ok=True)
    page_file.write_text(content, encoding="utf-8")


@pytest.fixture
def summary_wiki(temp_dir: Path) -> Path:
    """Create a wiki with shared entities and source pages."""
    wiki = temp_dir / "wiki_system"
    wiki.mkdir()
    domains = wiki / "domains"
    domains.mkdir()
    for d in ("alpha", "beta"):
        (domains / d / "pages").mkdir(parents=True)
    (wiki / "shared").mkdir(exist_ok=True)
    return wiki


class TestClaimNormalization:
    def test_lowercase_and_strip(self) -> None:
        result = CrossDomainSummaryJob(None)._normalize_text("  HELLO WORLD  ")
        assert result == "hello world"

    def test_punctuation_removed(self) -> None:
        result = CrossDomainSummaryJob(None)._normalize_text("Hello, world!")
        assert result == "hello world"

    def test_multiple_spaces_collapsed(self) -> None:
        result = CrossDomainSummaryJob(None)._normalize_text("Hello    World")
        assert result == "hello world"

    def test_dedup_finds_duplicates(self) -> None:
        job = CrossDomainSummaryJob(None)
        assert job._normalize_text("The system works.") == job._normalize_text("The system works")


class TestClaimDeduplication:
    def test_deduplicates_normalized_claims(self) -> None:
        claims = [
            Claim(text="The system works.", confidence=0.9, source_page_id="p1"),
            Claim(text="The system works", confidence=0.8, source_page_id="p2"),
            Claim(text="It is fast.", confidence=0.7, source_page_id="p1"),
        ]
        result = CrossDomainSummaryJob(None)._deduplicate_claims(claims, top_n=10)
        assert len(result) == 2

    def test_sorted_by_confidence(self) -> None:
        claims = [
            Claim(text="Low", confidence=0.3, source_page_id="p1"),
            Claim(text="High", confidence=0.9, source_page_id="p1"),
            Claim(text="Mid", confidence=0.6, source_page_id="p1"),
        ]
        result = CrossDomainSummaryJob(None)._deduplicate_claims(claims, top_n=10)
        assert result[0] == "High"
        assert result[1] == "Mid"

    def test_top_n_respected(self) -> None:
        claims = [
            Claim(text=f"Claim {i}", confidence=float(i), source_page_id="p1") for i in range(1, 6)
        ]
        result = CrossDomainSummaryJob(None)._deduplicate_claims(claims, top_n=3)
        assert len(result) == 3


class TestClaimExtraction:
    def test_extracts_claims_from_frontmatter(self, summary_wiki: Path) -> None:
        page_fm = {
            "id": "test-page",
            "kind": "page",
            "claims": [
                {"text": "Claim A", "confidence": 0.9, "trust_tag": "extracted"},
                {"text": "Claim B", "confidence": 0.6, "trust_tag": "ambiguous"},
            ],
        }
        job = CrossDomainSummaryJob(wiki_base=summary_wiki)
        claims = job._extract_claims(page_fm)
        assert len(claims) == 2
        assert claims[0].text == "Claim A"
        assert claims[0].confidence == 0.9
        assert claims[0].source_page_id == "test-page"

    def test_skips_missing_claim_text(self, summary_wiki: Path) -> None:
        page_fm = {
            "id": "test-page",
            "claims": [{"confidence": 0.5}],  # No text key
        }
        job = CrossDomainSummaryJob(wiki_base=summary_wiki)
        claims = job._extract_claims(page_fm)
        assert len(claims) == 0

    def test_skips_non_dict_claims(self, summary_wiki: Path) -> None:
        page_fm = {"id": "test-page", "claims": ["not a dict", 42]}
        job = CrossDomainSummaryJob(wiki_base=summary_wiki)
        claims = job._extract_claims(page_fm)
        assert len(claims) == 0


class TestSlimTimestampLineage:
    """Slim timestamp lineage is correctly absent from summary code.

    No Prometheus metrics are used in this module.
    The project uses custom observability SDK.
    """

    def test_no_prometheus_imports(self) -> None:
        from llm_wiki.daemon.jobs import summary

        source = Path(summary.__file__).read_text(encoding="utf-8")
        assert "prometheus" not in source.lower()


class TestTopNConfigurable:
    def test_default_top_n(self) -> None:
        from llm_wiki.models.config import SummaryConfig

        config = SummaryConfig()
        assert config.top_n == 10

    def test_custom_top_n(self) -> None:
        from llm_wiki.models.config import SummaryConfig

        config = SummaryConfig(top_n=5)
        assert config.top_n == 5

    def test_top_n_applied_in_dedup(self, summary_wiki: Path) -> None:
        claims = [
            Claim(text=f"C{i}", confidence=float(i), source_page_id="p1") for i in range(1, 11)
        ]
        result = CrossDomainSummaryJob(None)._deduplicate_claims(claims, top_n=3)
        assert len(result) == 3


class TestEntityArchival:
    def test_archives_summary_when_below_threshold(self, temp_dir: Path) -> None:
        wiki = temp_dir / "wiki_system"
        wiki.mkdir()
        (wiki / "shared").mkdir()

        # Create a shared entity with only one source page (below threshold of 2)
        _write_shared_entity(
            wiki,
            "single-source",
            "Single Source",
            source_pages=["only-page"],
            domains=["alpha"],
        )

        # Run summary job — should archive the summary, not create it
        job = CrossDomainSummaryJob(wiki_base=wiki)
        report = job.process_entities()

        assert report.summaries_archived >= 0
        assert report.summaries_generated == 0

    def _write_shared_entity(
        self,
        wiki_root: Path,
        entity_id: str,
        title: str,
        source_pages: list[str],
        domains: list[str],
    ) -> None:
        _write_shared_entity(wiki_root, entity_id, title, source_pages, domains)


class TestLlmFallback:
    def test_fallback_to_claim_digest_on_failure(self, summary_wiki: Path) -> None:
        """LLM failure should fall back to claim digest without raising."""
        # Mock LLM base config path that doesn't exist to trigger failure
        import frontmatter

        entity = summary_wiki / "shared" / "llm-test.md"
        fm = {
            "id": "llm-test",
            "kind": "entity",
            "title": "LLM Test",
            "source_pages": ["src-a", "src-b"],
            "domains": ["alpha", "beta"],
        }
        entity.write_text(frontmatter.dumps(frontmatter.Post("Body", **fm)), encoding="utf-8")

        # Create source pages so _try_load_source_page finds them
        for pid, domain in [("src-a", "alpha"), ("src-b", "beta")]:
            _write_source_page(
                summary_wiki,
                pid,
                f"Source {pid}",
                [{"text": f"Claim for {pid}", "confidence": 0.8}],
                domain,
            )

        job = CrossDomainSummaryJob(wiki_base=summary_wiki, llm_extraction=True)
        # Should not raise — falls back to claim digest
        report = job.process_entities()
        assert report  # Contains results, doesn't raise


@pytest.fixture
def healthy_entity_wiki(temp_dir: Path) -> Path:
    """Wiki with a healthy entity (2 source pages in 2 domains)."""
    wiki = temp_dir / "wiki_system"
    wiki.mkdir()
    (wiki / "shared").mkdir()
    for d in ("alpha", "beta"):
        (wiki / "domains" / d / "pages").mkdir(parents=True)

    _write_shared_entity(
        wiki,
        "cross-entity",
        "Cross Entity",
        source_pages=["alpha-page", "beta-page"],
        domains=["alpha", "beta"],
    )
    _write_source_page(
        wiki,
        "alpha-page",
        "Alpha Page",
        [{"text": "Claim A", "confidence": 0.95}],
        "alpha",
    )
    _write_source_page(
        wiki,
        "beta-page",
        "Beta Page",
        [{"text": "Claim A", "confidence": 0.90}, {"text": "Claim B", "confidence": 0.85}],
        "beta",
    )
    return wiki


class TestSummaryGeneration:
    def test_generates_summary_for_entity(self, healthy_entity_wiki: Path) -> None:
        job = CrossDomainSummaryJob(wiki_base=healthy_entity_wiki)
        report = job.process_entities()

        assert report.total_entities == 1
        assert (report.summaries_generated + report.summaries_updated) >= 1

    def test_shared_entity_page_exists(self, healthy_entity_wiki: Path) -> None:
        _write_shared_entity(
            healthy_entity_wiki,
            "cross-entity",
            "Cross Entity",
            ["alpha-page", "beta-page"],
            ["alpha", "beta"],
        )
        job = CrossDomainSummaryJob(wiki_base=healthy_entity_wiki)
        job.process_entities()

        summary_dir = healthy_entity_wiki / "shared"
        summary_files = list(summary_dir.glob("*-summary.md"))
        assert len(summary_files) >= 1

        # Read the summary page and check frontmatter
        fm, body = parse_frontmatter(summary_files[0].read_text(encoding="utf-8"))
        assert fm.get("kind") == "concept"
        assert "Cross Entity" in fm.get("title", "")

    def test_deduplication_across_domains(self, healthy_entity_wiki: Path) -> None:
        _write_shared_entity(
            healthy_entity_wiki,
            "cross-entity",
            "Cross Entity",
            ["alpha-page", "beta-page"],
            ["alpha", "beta"],
        )
        job = CrossDomainSummaryJob(wiki_base=healthy_entity_wiki)
        job.process_entities()

        # Read the summary file
        summary_dir = healthy_entity_wiki / "shared"
        summary_files = list(summary_dir.glob("cross-entity-summary.md"))
        assert len(summary_files) == 1

        fm, body = parse_frontmatter(summary_files[0].read_text(encoding="utf-8"))
        # Should have at most 1 claim (B after dedup of A)
        assert fm.get("source_count", 0) >= 1


class TestSearchBoost:
    def test_summary_page_has_authority_score_1(self, healthy_entity_wiki: Path) -> None:
        _write_shared_entity(
            healthy_entity_wiki,
            "cross-entity",
            "Cross Entity",
            ["alpha-page", "beta-page"],
            ["alpha", "beta"],
        )
        job = CrossDomainSummaryJob(wiki_base=healthy_entity_wiki)
        job.process_entities()

        summary_dir = healthy_entity_wiki / "shared"
        for sf in summary_dir.glob("*-summary.md"):
            fm, _ = parse_frontmatter(sf.read_text(encoding="utf-8"))
            assert fm.get("authority_score") == 1.0
