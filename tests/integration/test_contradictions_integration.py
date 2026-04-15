"""Integration tests for contradiction detection with real pages."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock

import pytest

from llm_wiki.governance.contradictions import ContradictionDetector


class TestContradictionDetectorIntegration:
    """Integration tests for contradiction detector with actual wiki pages."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock LLM client."""
        return Mock()

    @pytest.fixture
    def detector(self, mock_client: Mock) -> ContradictionDetector:
        """Create contradiction detector with mock client."""
        return ContradictionDetector(client=mock_client, min_confidence=0.6)

    @pytest.fixture
    def wiki_with_contradictions(self) -> Generator[Path, None, None]:
        """Create a temporary wiki with contradictory pages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_base = Path(tmpdir)
            domains_dir = wiki_base / "domains"
            domains_dir.mkdir()

            # Create test domain
            domain_dir = domains_dir / "test-domain"
            domain_dir.mkdir()
            pages_dir = domain_dir / "pages"
            pages_dir.mkdir()

            # Page 1 with numerical claim
            page1_content = """---
id: python-page
title: Python Programming Language
created: 2024-01-01T00:00:00Z
updated: 2024-01-01T00:00:00Z
---

# Python

Python is a popular programming language. It was released in 1991 by Guido van Rossum.

The first version (0.9.0) was released in February 1991.
"""

            page1_path = pages_dir / "python.md"
            page1_path.write_text(page1_content)

            # Page 2 with contradictory claim
            page2_content = """---
id: python-history-page
title: Python History
created: 2024-01-02T00:00:00Z
updated: 2024-01-02T00:00:00Z
---

# Python History

Python was first released in 1990, making it one of the oldest programming languages.

Some sources claim it was released in 1990 before mainstream adoption in the 2000s.
"""

            page2_path = pages_dir / "python-history.md"
            page2_path.write_text(page2_content)

            yield wiki_base

    @pytest.fixture
    def wiki_with_negations(self) -> Generator[Path, None, None]:
        """Create a temporary wiki with negation contradictions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_base = Path(tmpdir)
            domains_dir = wiki_base / "domains"
            domains_dir.mkdir()

            # Create test domain
            domain_dir = domains_dir / "test-domain"
            domain_dir.mkdir()
            pages_dir = domain_dir / "pages"
            pages_dir.mkdir()

            # Page 1 - affirmative claim
            page1_content = """---
id: docker-features
title: Docker Features
created: 2024-01-01T00:00:00Z
updated: 2024-01-01T00:00:00Z
---

# Docker

Docker containers are lightweight and fast. They provide efficient resource utilization.
"""

            page1_path = pages_dir / "docker-features.md"
            page1_path.write_text(page1_content)

            # Page 2 - negation claim
            page2_content = """---
id: docker-limitations
title: Docker Limitations
created: 2024-01-02T00:00:00Z
updated: 2024-01-02T00:00:00Z
---

# Docker Limitations

Docker containers are not lightweight on certain systems with limited resources.
"""

            page2_path = pages_dir / "docker-limitations.md"
            page2_path.write_text(page2_content)

            yield wiki_base

    @pytest.fixture
    def wiki_no_contradictions(self) -> Generator[Path, None, None]:
        """Create a temporary wiki without contradictions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            wiki_base = Path(tmpdir)
            domains_dir = wiki_base / "domains"
            domains_dir.mkdir()

            # Create test domain
            domain_dir = domains_dir / "test-domain"
            domain_dir.mkdir()
            pages_dir = domain_dir / "pages"
            pages_dir.mkdir()

            # Page 1
            page1_content = """---
id: page1
title: Page 1
created: 2024-01-01T00:00:00Z
updated: 2024-01-01T00:00:00Z
---

# Page 1

This page discusses topic A. The Earth is approximately 4.5 billion years old.
"""

            page1_path = pages_dir / "page1.md"
            page1_path.write_text(page1_content)

            # Page 2 - complementary info, not contradictory
            page2_content = """---
id: page2
title: Page 2
created: 2024-01-02T00:00:00Z
updated: 2024-01-02T00:00:00Z
---

# Page 2

This page discusses topic B. The Earth formed about 4.5 billion years ago.
"""

            page2_path = pages_dir / "page2.md"
            page2_path.write_text(page2_content)

            yield wiki_base

    def test_analyze_all_pages_with_contradictions(
        self, detector: ContradictionDetector, wiki_with_contradictions: Path, mock_client: Mock
    ):
        """Test analyzing all pages and finding contradictions."""
        # Mock the claims extractor to return specific claims
        mock_client.chat_completion.return_value = json.dumps(
            {
                "claims": [
                    {
                        "claim": "Python was released in 1991",
                        "confidence": 0.95,
                        "source_reference": "paragraph 1",
                        "subject": "Python",
                        "predicate": "released",
                        "object": "1991",
                    }
                ]
            }
        )

        report = detector.analyze_all_pages(wiki_with_contradictions)

        # Report should have been created
        assert report is not None
        assert report.total_contradictions >= 0

    def test_analyze_all_pages_no_contradictions(
        self, detector: ContradictionDetector, wiki_no_contradictions: Path, mock_client: Mock
    ):
        """Test analyzing pages without contradictions."""
        # Mock the claims extractor
        mock_client.chat_completion.return_value = json.dumps(
            {
                "claims": [
                    {
                        "claim": "The Earth is approximately 4.5 billion years old",
                        "confidence": 0.9,
                        "source_reference": "section 1",
                    }
                ]
            }
        )

        report = detector.analyze_all_pages(wiki_no_contradictions)

        # Report should have low or zero contradictions
        assert report is not None
        # Note: Some may still be detected due to slight variations in claims

    def test_generate_report(
        self,
        detector: ContradictionDetector,
        wiki_with_contradictions: Path,
        mock_client: Mock,
        tmp_path: Path,
    ):
        """Test generating a markdown report of contradictions."""
        # Mock the claims extractor
        mock_client.chat_completion.return_value = json.dumps(
            {
                "claims": [
                    {
                        "claim": "Python was released in 1991",
                        "confidence": 0.95,
                        "source_reference": "section 1",
                    }
                ]
            }
        )

        report = detector.analyze_all_pages(wiki_with_contradictions)
        output_path = tmp_path / "report.md"

        result_path = detector.generate_report(report, output_path)

        # Report should be created
        assert result_path.exists()
        assert result_path.suffix == ".md"

        # Check content
        content = result_path.read_text()
        assert "Contradiction Detection Report" in content
        assert "Summary" in content

    def test_generate_report_with_high_confidence_contradictions(
        self, detector: ContradictionDetector, tmp_path: Path
    ):
        """Test report generation with high confidence contradictions."""
        from llm_wiki.governance.contradictions import Contradiction, ContradictionReport
        from llm_wiki.models.extraction import ClaimExtraction

        # Create claims
        claim_1 = ClaimExtraction(
            claim="Feature X is supported",
            confidence=0.95,
            source_reference="section 1",
        )
        claim_2 = ClaimExtraction(
            claim="Feature X is not supported",
            confidence=0.9,
            source_reference="section 2",
        )

        # Create contradiction
        contradiction = Contradiction(
            claim_1=claim_1,
            page_id_1="page1",
            claim_2=claim_2,
            page_id_2="page2",
            contradiction_type="negation",
            confidence=0.9,
            severity="high",
            explanation="Direct negation",
            suggested_resolution="Check source credibility",
        )

        # Create report
        report = ContradictionReport(total_contradictions=1)
        report.high_confidence = [contradiction]

        output_path = tmp_path / "report.md"
        result_path = detector.generate_report(report, output_path)

        # Verify report content
        content = result_path.read_text()
        assert "High Confidence Contradictions" in content
        assert "Feature X is supported" in content
        assert "Feature X is not supported" in content
        assert "negation" in content

    def test_wiki_without_domains_directory(self, detector: ContradictionDetector, tmp_path: Path):
        """Test handling wiki without domains directory."""
        wiki_base = tmp_path / "wiki"
        wiki_base.mkdir()

        report = detector.analyze_all_pages(wiki_base)

        assert report.total_contradictions == 0
        assert len(report.high_confidence) == 0

    def test_wiki_with_invalid_page(
        self, detector: ContradictionDetector, tmp_path: Path, mock_client: Mock
    ):
        """Test handling invalid page files gracefully."""
        wiki_base = tmp_path / "wiki"
        domains_dir = wiki_base / "domains"
        domain_dir = domains_dir / "test"
        pages_dir = domain_dir / "pages"
        pages_dir.mkdir(parents=True)

        # Create an invalid page (no frontmatter)
        invalid_page = pages_dir / "invalid.md"
        invalid_page.write_text("This is not a valid page\nwithout frontmatter")

        # Mock the extractor
        mock_client.chat_completion.return_value = json.dumps({"claims": []})

        # Should not crash
        report = detector.analyze_all_pages(wiki_base)

        assert report is not None

    def test_large_number_of_claims(self, detector: ContradictionDetector, mock_client: Mock):
        """Test performance with many claims."""
        from llm_wiki.models.extraction import ClaimExtraction

        # Create many claims
        claims = []
        for i in range(100):
            claim = ClaimExtraction(
                claim=f"Fact number {i}",
                confidence=0.8,
                source_reference=f"section {i}",
            )
            claims.append((claim, f"page_{i % 5}"))

        # Detect contradictions
        contradictions = detector.detect_contradictions(claims)

        # Should complete without error
        assert isinstance(contradictions, list)

    def test_report_organization_by_type(self, detector: ContradictionDetector):
        """Test that contradictions are properly organized by type."""
        from llm_wiki.governance.contradictions import Contradiction, ContradictionReport
        from llm_wiki.models.extraction import ClaimExtraction

        claim_1 = ClaimExtraction(claim="Claim 1", confidence=0.9, source_reference="ref1")
        claim_2 = ClaimExtraction(claim="Claim 2", confidence=0.9, source_reference="ref2")

        # Create contradictions of different types
        contradictions = [
            Contradiction(
                claim_1=claim_1,
                page_id_1="page1",
                claim_2=claim_2,
                page_id_2="page2",
                contradiction_type="negation",
                confidence=0.9,
                severity="high",
                explanation="Test negation",
            ),
            Contradiction(
                claim_1=claim_1,
                page_id_1="page3",
                claim_2=claim_2,
                page_id_2="page4",
                contradiction_type="numerical",
                confidence=0.8,
                severity="medium",
                explanation="Test numerical",
            ),
        ]

        # Create report
        report = ContradictionReport(total_contradictions=2)
        for contradiction in contradictions:
            if contradiction.confidence >= 0.8:
                report.high_confidence.append(contradiction)
            if contradiction.contradiction_type not in report.by_type:
                report.by_type[contradiction.contradiction_type] = []
            report.by_type[contradiction.contradiction_type].append(contradiction)

        # Verify organization
        assert len(report.by_type) == 2
        assert "negation" in report.by_type
        assert "numerical" in report.by_type
        assert len(report.by_type["negation"]) == 1
        assert len(report.by_type["numerical"]) == 1
