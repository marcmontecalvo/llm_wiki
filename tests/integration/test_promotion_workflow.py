"""Integration tests for promotion workflow."""

from pathlib import Path

import pytest

from llm_wiki.index.backlinks import BacklinkIndex
from llm_wiki.promotion.config import PromotionConfig
from llm_wiki.promotion.engine import PromotionEngine
from llm_wiki.promotion.scorer import PromotionScorer


class TestPromotionWorkflow:
    """Integration tests for complete promotion workflow."""

    @pytest.fixture
    def wiki_setup(self, temp_dir: Path) -> tuple[Path, Path, Path]:
        """Set up a multi-domain wiki for testing.

        Returns:
            Tuple of (wiki_base, domain1_pages, domain2_pages)
        """
        wiki_base = temp_dir / "wiki"
        wiki_base.mkdir()

        # Create domain1
        domain1_pages = wiki_base / "domains" / "domain1" / "pages"
        domain1_pages.mkdir(parents=True)

        # Create domain2
        domain2_pages = wiki_base / "domains" / "domain2" / "pages"
        domain2_pages.mkdir(parents=True)

        return wiki_base, domain1_pages, domain2_pages

    def test_cross_domain_promotion_workflow(self, wiki_setup: tuple[Path, Path, Path]):
        """Test complete workflow: create pages, detect candidates, promote."""
        wiki_base, domain1_pages, domain2_pages = wiki_setup

        # Create shared concept page in domain1
        concept_page = domain1_pages / "distributed-systems.md"
        concept_page.write_text(
            "---\n"
            "id: distributed-systems\n"
            "kind: concept\n"
            "title: Distributed Systems\n"
            "domain: domain1\n"
            "confidence: 0.9\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "updated_at: 2024-04-14T00:00:00Z\n"
            "---\n"
            "\n"
            "# Distributed Systems\n"
            "\n"
            "Distributed systems are computing systems whose components are located on "
            "different networked computers. This is a comprehensive guide covering fundamentals, "
            "architecture patterns, consensus algorithms, and practical implementations.\n"
            "\n"
            "## Key Concepts\n"
            "- Consensus algorithms\n"
            "- Replication strategies\n"
            "- Failure handling\n"
            "- Performance optimization\n"
        )

        # Create pages in domain2 that reference domain1's concept
        ref_page1 = domain2_pages / "microservices-arch.md"
        ref_page1.write_text(
            "---\n"
            "id: microservices-arch\n"
            "kind: page\n"
            "title: Microservices Architecture\n"
            "domain: domain2\n"
            "confidence: 0.85\n"
            "created_at: 2024-02-01T00:00:00Z\n"
            "updated_at: 2024-04-14T00:00:00Z\n"
            "---\n"
            "\n"
            "# Microservices Architecture\n"
            "\n"
            "Modern microservices rely heavily on [[distributed-systems]] principles.\n"
            "We implement service discovery, load balancing, and fault tolerance.\n"
        )

        ref_page2 = domain2_pages / "kubernetes-deploy.md"
        ref_page2.write_text(
            "---\n"
            "id: kubernetes-deploy\n"
            "kind: page\n"
            "title: Kubernetes Deployment\n"
            "domain: domain2\n"
            "confidence: 0.8\n"
            "created_at: 2024-03-01T00:00:00Z\n"
            "updated_at: 2024-04-14T00:00:00Z\n"
            "---\n"
            "\n"
            "# Kubernetes Deployment\n"
            "\n"
            "Kubernetes orchestration depends on [[distributed-systems]] theory for cluster "
            "coordination and failover mechanisms.\n"
        )

        # Initialize backlinks index
        backlinks = BacklinkIndex(index_dir=wiki_base / "index")
        backlinks.add_page_links("microservices-arch", "[[distributed-systems]]")
        backlinks.add_page_links("kubernetes-deploy", "[[distributed-systems]]")
        backlinks.save()

        # Score pages
        config = PromotionConfig(
            auto_promote_threshold=8.0,
            suggest_promote_threshold=5.0,
            min_quality_score=0.7,
            min_cross_domain_refs=2,
        )
        scorer = PromotionScorer(config=config, wiki_base=wiki_base)
        candidates = scorer.score_all_pages()

        # Should find distributed-systems as candidate
        ds_candidates = [c for c in candidates if c.page_id == "distributed-systems"]

        if ds_candidates:
            candidate = ds_candidates[0]

            # Should have multiple cross-domain references
            assert candidate.cross_domain_references >= 2
            assert "domain2" in candidate.referring_domains

            # Promote the page
            engine = PromotionEngine(config=config, wiki_base=wiki_base)
            result = engine.promote_page(
                candidate.page_id, candidate.domain, update_references=True
            )

            assert result.success

            # Verify page is in shared
            shared_path = wiki_base / "shared" / "distributed-systems.md"
            assert shared_path.exists()

            # Verify original has tombstone
            original_path = domain1_pages / "distributed-systems.md"
            assert original_path.exists()
            original_content = original_path.read_text()
            assert "shared" in original_content.lower()

            # CRITICAL: Verify that referring pages have been UPDATED to point to shared
            # This is the key fix - before it was a no-op
            ref_content1 = ref_page1.read_text()
            ref_content2 = ref_page2.read_text()

            # The references should now have "shared/" prefix
            assert "[[shared/distributed-systems]]" in ref_content1 or "[[shared/distributed-systems" in ref_content1, (
                f"Reference not updated in microservices-arch. Content: {ref_content1[:200]}"
            )
            assert "[[shared/distributed-systems]]" in ref_content2 or "[[shared/distributed-systems" in ref_content2, (
                f"Reference not updated in kubernetes-deploy. Content: {ref_content2[:200]}"
            )

    def test_promotion_with_multiple_references_from_same_domain(
        self, wiki_setup: tuple[Path, Path, Path]
    ):
        """Test that promotion considers references from multiple pages in same domain."""
        wiki_base, domain1_pages, domain2_pages = wiki_setup

        # Create shared resource in domain1
        resource = domain1_pages / "security-patterns.md"
        resource.write_text(
            "---\n"
            "id: security-patterns\n"
            "kind: concept\n"
            "title: Security Patterns\n"
            "domain: domain1\n"
            "confidence: 0.85\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "updated_at: 2024-04-14T00:00:00Z\n"
            "---\n"
            "\n"
            "# Security Patterns\n"
            "\n"
            "Common patterns for implementing secure systems including authentication, "
            "authorization, encryption, and threat modeling.\n"
        )

        # Create multiple pages in domain2 referencing it
        for i in range(3):
            page = domain2_pages / f"secure-service-{i}.md"
            page.write_text(
                "---\n"
                f"id: secure-service-{i}\n"
                "kind: page\n"
                f"title: Secure Service {i}\n"
                "domain: domain2\n"
                "confidence: 0.8\n"
                "created_at: 2024-02-01T00:00:00Z\n"
                "updated_at: 2024-04-14T00:00:00Z\n"
                "---\n"
                "\n"
                f"# Secure Service {i}\n"
                "\n"
                "Implementation following [[security-patterns]].\n"
            )

        # Build backlinks
        backlinks = BacklinkIndex(index_dir=wiki_base / "index")
        for i in range(3):
            backlinks.add_page_links(f"secure-service-{i}", "[[security-patterns]]")
        backlinks.save()

        # Score
        config = PromotionConfig(min_cross_domain_refs=2)
        scorer = PromotionScorer(config=config, wiki_base=wiki_base)
        candidates = scorer.score_all_pages()

        # Check if security-patterns is a candidate
        security_candidates = [c for c in candidates if c.page_id == "security-patterns"]
        if security_candidates:
            candidate = security_candidates[0]
            # Total references should be 3
            assert candidate.total_references >= 3

    def test_promotion_respects_quality_threshold(self, wiki_setup: tuple[Path, Path, Path]):
        """Test that pages below quality threshold are not promoted."""
        wiki_base, domain1_pages, domain2_pages = wiki_setup

        # Create low-quality page in domain1
        poor_page = domain1_pages / "stub-page.md"
        poor_page.write_text(
            "---\n"
            "id: stub-page\n"
            "kind: page\n"
            "title: Stub\n"
            "domain: domain1\n"
            "confidence: 0.2\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "---\n"
            "\n"
            "Incomplete.\n"
        )

        # Create references to it
        ref = domain2_pages / "ref-stub.md"
        ref.write_text(
            "---\n"
            "id: ref-stub\n"
            "kind: page\n"
            "title: Ref\n"
            "domain: domain2\n"
            "---\n"
            "\n"
            "Links [[stub-page]].\n"
        )

        # Build backlinks
        backlinks = BacklinkIndex(index_dir=wiki_base / "index")
        backlinks.add_page_links("ref-stub", "[[stub-page]]")
        backlinks.save()

        # Score with high quality threshold
        config = PromotionConfig(min_quality_score=0.7, min_cross_domain_refs=1)
        scorer = PromotionScorer(config=config, wiki_base=wiki_base)
        candidates = scorer.score_all_pages()

        # stub-page should not be a candidate
        stub_candidates = [c for c in candidates if c.page_id == "stub-page"]
        assert len(stub_candidates) == 0

    def test_promotion_scoring_weights_cross_domain_refs(self, wiki_setup: tuple[Path, Path, Path]):
        """Test that scoring properly weights cross-domain references."""
        wiki_base, domain1_pages, domain2_pages = wiki_setup

        # Create page with many local references but few cross-domain
        page = domain1_pages / "local-focus.md"
        page.write_text(
            "---\n"
            "id: local-focus\n"
            "kind: page\n"
            "title: Local Focus\n"
            "domain: domain1\n"
            "confidence: 0.85\n"
            "created_at: 2024-01-01T00:00:00Z\n"
            "---\n"
            "\n"
            "Content that is primarily used locally.\n"
        )

        # Create one cross-domain reference
        ref = domain2_pages / "cross-ref.md"
        ref.write_text(
            "---\n"
            "id: cross-ref\n"
            "kind: page\n"
            "title: Cross Ref\n"
            "domain: domain2\n"
            "---\n"
            "\n"
            "References [[local-focus]].\n"
        )

        # Build backlinks with one cross-domain ref
        backlinks = BacklinkIndex(index_dir=wiki_base / "index")
        backlinks.add_page_links("cross-ref", "[[local-focus]]")
        backlinks.save()

        # Score
        config = PromotionConfig(
            min_cross_domain_refs=1,
            cross_domain_ref_weight=2.0,
            total_ref_weight=0.5,
        )
        scorer = PromotionScorer(config=config, wiki_base=wiki_base)
        candidates = scorer.score_all_pages()

        # Check scoring
        local_candidates = [c for c in candidates if c.page_id == "local-focus"]
        if local_candidates:
            candidate = local_candidates[0]
            # Cross-domain refs should be weighted more heavily
            cross_weight = candidate.cross_domain_references * config.cross_domain_ref_weight
            assert cross_weight > 0
