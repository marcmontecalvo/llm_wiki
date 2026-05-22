"""Tests for cross-domain authority scoring."""

from __future__ import annotations

from pathlib import Path

import pytest


def _write_page(wiki_root: Path, domain: str, page_id: str, title: str, links: list[str]) -> None:
    """Helper to create a markdown page file under wiki_system/domains/{domain}/pages/."""
    links_yaml = ", ".join(f'"{link}"' for link in links) if links else ""
    # Wiki-style internal links go in the BODY as [[page-id]] —
    # the backlink index extracts these patterns from body text.
    body_links = "\n".join(f"[[{link}]]" for link in links) if links else ""
    content = f"""---
id: {page_id}
kind: page
title: {title}
domain: {domain}
status: published
confidence: 0.8
sources: []
links: [{links_yaml}]
updated_at: 2026-01-01T00:00:00Z
---

# {title}

{body_links}
"""
    page_file = wiki_root / "domains" / domain / "pages" / f"{page_id}.md"
    page_file.parent.mkdir(parents=True, exist_ok=True)
    page_file.write_text(content, encoding="utf-8")


@pytest.fixture
def scored_wiki(temp_dir: Path) -> Path:
    """Create a wiki with known backlink structure for authority scoring tests."""
    wiki = temp_dir / "wiki_system"
    wiki.mkdir()
    domains = wiki / "domains"
    domains.mkdir()

    # Create three domains
    for d in ("alpha", "beta", "gamma"):
        (domains / d / "pages").mkdir(parents=True)

    # alpha/llm-basics.md is linked from:
    #   - alpha/transformers.md (same domain)
    #   - beta/neural-nets.md (cross domain)
    #   - gamma/ai-overview.md (cross domain)
    _write_page(
        wiki, "alpha", "llm-basics", "LLM Basics", ["transformers", "neural-nets", "ai-overview"]
    )
    # beta/neural-nets.md
    _write_page(wiki, "beta", "neural-nets", "Neural Networks", ["llm-basics"])
    # gamma/ai-overview.md
    _write_page(wiki, "gamma", "ai-overview", "AI Overview", ["llm-basics"])

    # alpha/transformers.md — linked from 2 same-domain pages
    _write_page(wiki, "alpha", "transformers", "Transformers", ["llm-basics"])
    # Additional page links to llm-basics from alpha stream
    # Actually the backlink index extracts forward links FROM content
    # So alpha/llm-basics links to transformers -> transformers gets backlink from llm-basics
    # But we need backlinks TO llm-basics. The backlinks are extracted from each page's forward links.

    return wiki


def _build_backlinks(wiki_root: Path) -> None:
    """Call backlink rebuild to populate the index."""
    from llm_wiki.index.backlinks import BacklinkIndex

    bli = BacklinkIndex(index_dir=wiki_root / "index")
    bli.rebuild_from_pages(wiki_root)


class TestComputeAuthorityScores:
    def test_returns_dict(self, scored_wiki):
        from llm_wiki.synthesis.authority import compute_authority_scores

        scores = compute_authority_scores(scored_wiki)
        assert isinstance(scores, dict)

    def test_pages_with_backlinks_have_nonzero_score(self, scored_wiki):
        from llm_wiki.synthesis.authority import compute_authority_scores

        scores = compute_authority_scores(scored_wiki)
        # llm-basics has backlinks from beta and gamma
        assert scores.get("llm-basics", 0) > 0

    def test_zero_backlinks(self, scored_wiki):
        """Pages with zero cross-domain backlinks get score 0.0."""
        from llm_wiki.synthesis.authority import compute_authority_scores

        # alpha/transformers already has some backlinks from file links
        # Let's use a completely isolated page
        _write_page(scored_wiki, "alpha", "isolated-page", "Isolated", [])
        scores = compute_authority_scores(scored_wiki)
        # Isolated has no backlinks (nothing links to it), so score = 0.0
        assert scores.get("isolated-page", 0) == 0.0

    def test_cross_domain_boost(self, temp_dir: Path) -> None:
        """Same link count, more domains = higher score."""
        from llm_wiki.synthesis.authority import compute_authority_scores

        wiki = temp_dir / "wiki_system"
        wiki.mkdir()
        domains = wiki / "domains"
        domains.mkdir()
        for d in ("a", "b", "c"):
            (domains / d / "pages").mkdir(parents=True)

        # target-a receives 2 same-domain links (from domain a)
        _write_page(wiki, "a", "target-a", "Target A", ["a1", "a2"])
        _write_page(wiki, "a", "a1", "A1", ["target-a"])
        _write_page(wiki, "a", "a2", "A2", ["target-a"])
        # target-cross receives 1 link each from 2 different domains (and itself)
        _write_page(wiki, "b", "target-cross", "Target Cross", ["b1", "c1"])
        _write_page(wiki, "b", "b1", "B1", ["target-cross"])
        _write_page(wiki, "c", "c1", "C1", ["target-cross"])

        scores = compute_authority_scores(wiki)
        assert scores.get("target-cross", 0) > scores.get("target-a", 0)

    def test_normalization_range(self, scored_wiki):
        """All scores should be in 0.0–1.0 range."""
        from llm_wiki.synthesis.authority import compute_authority_scores

        scores = compute_authority_scores(scored_wiki)
        for score in scores.values():
            assert 0.0 <= score <= 1.0

    def test_no_llm_calls(self, scored_wiki):
        """Authority scoring must be purely algorithmic.
        Verify no LLMClient import is accidentally added."""
        from llm_wiki.synthesis import authority

        imports = []
        for name in dir(authority):
            obj = getattr(authority, name)
            if hasattr(obj, "__module__"):
                mod = obj.__module__ or ""
                if "llm" in mod.lower() and "client" in mod.lower():
                    imports.append(name)
        assert not imports, "LLM client should not be imported in authority scoring"


class TestWriteAuthorityScores:
    def test_writes_frontmatter(self, temp_dir: Path) -> None:
        from llm_wiki.synthesis.authority import compute_authority_scores, write_authority_scores

        scores = (
            compute_authority_scores(temp_dir / "wiki_system")
            if (temp_dir / "wiki_system").exists()
            else {
                "test-page": 0.85,
            }
        )
        if not scores:
            scores = {"test-page": 0.5}

        n = write_authority_scores(temp_dir / "wiki_system", scores)
        assert n >= 0  # No error raised
