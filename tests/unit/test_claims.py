"""Tests for claims extraction."""

import json
from unittest.mock import Mock

import pytest

from llm_wiki.extraction.claims import ClaimsExtractor
from llm_wiki.models.extraction import Claim


class TestClaimsExtractor:
    """Tests for ClaimsExtractor."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock LLM client."""
        return Mock()

    @pytest.fixture
    def extractor(self, mock_client: Mock) -> ClaimsExtractor:
        """Create claims extractor with mock client."""
        return ClaimsExtractor(client=mock_client)

    def test_extract_claims_success(self, extractor: ClaimsExtractor, mock_client: Mock):
        """Test successful claims extraction."""
        mock_client.chat_completion.return_value = """{
            "claims": [
                {
                    "claim": "Python was released in 1991",
                    "confidence": 0.95,
                    "source_reference": "paragraph 1",
                    "subject": "Python",
                    "predicate": "released",
                    "object": "1991",
                    "temporal_context": "initial release",
                    "qualifiers": []
                },
                {
                    "claim": "Docker containers are lightweight",
                    "confidence": 0.85,
                    "source_reference": "section 2, paragraph 1",
                    "temporal_context": null,
                    "qualifiers": ["compared to VMs"]
                }
            ]
        }"""

        content = "Python was released in 1991. Docker containers are lightweight compared to VMs."
        metadata = {"title": "Technologies", "id": "tech-page"}

        claims = extractor.extract_claims(content, metadata)

        assert len(claims) == 2
        assert claims[0].claim == "Python was released in 1991"
        assert claims[0].confidence == 0.95
        assert claims[0].source_reference == "paragraph 1"
        assert claims[1].claim == "Docker containers are lightweight"
        assert claims[1].qualifiers == ["compared to VMs"]

    def test_extract_claims_with_page_id(self, extractor: ClaimsExtractor, mock_client: Mock):
        """Test claims extraction with explicit page_id."""
        mock_client.chat_completion.return_value = """{
            "claims": [
                {
                    "claim": "Test claim",
                    "confidence": 0.8,
                    "source_reference": "section 1"
                }
            ]
        }"""

        content = "Test content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata, page_id="custom-id")

        assert len(claims) == 1
        assert claims[0].claim == "Test claim"

    def test_extract_claims_confidence_validation(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test that confidence values are valid (0-1)."""
        mock_client.chat_completion.return_value = """{
            "claims": [
                {
                    "claim": "High confidence",
                    "confidence": 1.0,
                    "source_reference": "section 1"
                },
                {
                    "claim": "Low confidence",
                    "confidence": 0.0,
                    "source_reference": "section 2"
                },
                {
                    "claim": "Medium confidence",
                    "confidence": 0.5,
                    "source_reference": "section 3"
                }
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        assert len(claims) == 3
        assert claims[0].confidence == 1.0
        assert claims[1].confidence == 0.0
        assert claims[2].confidence == 0.5
        # All should be valid ClaimExtraction objects
        assert all(0.0 <= c.confidence <= 1.0 for c in claims)

    def test_extract_claims_list_format(self, extractor: ClaimsExtractor, mock_client: Mock):
        """Test claims extraction with list format response."""
        mock_client.chat_completion.return_value = """[
            {
                "claim": "Claim 1",
                "confidence": 0.9,
                "source_reference": "paragraph 1"
            }
        ]"""

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        assert len(claims) == 1
        assert claims[0].claim == "Claim 1"

    def test_extract_claims_max_limit(self, extractor: ClaimsExtractor, mock_client: Mock):
        """Test claims extraction respects max limit."""
        # Return 25 claims
        mock_claims = [
            {
                "claim": f"Claim {i}",
                "confidence": 0.8,
                "source_reference": f"section {i}",
            }
            for i in range(25)
        ]
        mock_client.chat_completion.return_value = json.dumps({"claims": mock_claims})

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        # Should be limited to 20
        assert len(claims) == 20

    def test_extract_claims_with_temporal_context(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test claims extraction preserves temporal context."""
        mock_client.chat_completion.return_value = """{
            "claims": [
                {
                    "claim": "The pandemic started in 2020",
                    "confidence": 0.95,
                    "source_reference": "section 1",
                    "temporal_context": "2020"
                }
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        assert len(claims) == 1
        assert claims[0].temporal_context == "2020"

    def test_extract_claims_with_qualifiers(self, extractor: ClaimsExtractor, mock_client: Mock):
        """Test claims extraction preserves qualifiers."""
        mock_client.chat_completion.return_value = """{
            "claims": [
                {
                    "claim": "Coffee contains caffeine",
                    "confidence": 0.95,
                    "source_reference": "section 1",
                    "qualifiers": ["in most varieties", "typically"]
                }
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        assert len(claims) == 1
        assert claims[0].qualifiers == ["in most varieties", "typically"]

    def test_extract_claims_error_returns_empty(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test error handling returns empty list."""
        mock_client.chat_completion.side_effect = Exception("API error")

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        assert claims == []

    def test_extract_claims_invalid_json(self, extractor: ClaimsExtractor, mock_client: Mock):
        """Test handling of invalid JSON response."""
        mock_client.chat_completion.return_value = "not json"

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        assert claims == []

    def test_extract_claims_validates_structure(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test that invalid claims are filtered out."""
        mock_client.chat_completion.return_value = """{
            "claims": [
                {
                    "claim": "Valid claim",
                    "confidence": 0.8,
                    "source_reference": "section 1"
                },
                {
                    "claim": "Missing source",
                    "confidence": 0.8
                },
                {
                    "confidence": 0.8,
                    "source_reference": "section 3"
                },
                "invalid"
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        # Only valid claim should be extracted
        assert len(claims) == 1
        assert claims[0].claim == "Valid claim"

    def test_extract_claims_handles_invalid_confidence(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test handling of invalid confidence values."""
        mock_client.chat_completion.return_value = """{
            "claims": [
                {
                    "claim": "Valid with default confidence",
                    "source_reference": "section 1"
                }
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        claims = extractor.extract_claims(content, metadata)

        assert len(claims) == 1
        assert claims[0].confidence == 0.5  # Default value

    def test_extract_claim_types_success(self, extractor: ClaimsExtractor, mock_client: Mock):
        """Test successful claim type extraction."""
        mock_client.chat_completion.return_value = """{
            "facts": [
                "Python was released in 1991",
                "Water boils at 100 degrees Celsius"
            ],
            "opinions": [
                "Python is the best programming language",
                "This approach is elegant"
            ],
            "instructions": [
                "First, install Python",
                "Then, run the script"
            ]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        result = extractor.extract_claim_types(content, metadata)

        assert len(result["facts"]) == 2
        assert len(result["opinions"]) == 2
        assert len(result["instructions"]) == 2
        assert "Python was released in 1991" in result["facts"]
        assert "Python is the best programming language" in result["opinions"]
        assert "First, install Python" in result["instructions"]

    def test_extract_claim_types_partial_response(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test claim type extraction with partial response."""
        mock_client.chat_completion.return_value = """{
            "facts": ["Fact 1", "Fact 2"],
            "opinions": []
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        result = extractor.extract_claim_types(content, metadata)

        assert len(result["facts"]) == 2
        assert len(result["opinions"]) == 0
        assert len(result["instructions"]) == 0

    def test_extract_claim_types_empty_response(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test claim type extraction with empty response."""
        mock_client.chat_completion.return_value = """{}"""

        content = "Content"
        metadata = {"title": "Test"}

        result = extractor.extract_claim_types(content, metadata)

        assert len(result["facts"]) == 0
        assert len(result["opinions"]) == 0
        assert len(result["instructions"]) == 0

    def test_extract_claim_types_error_returns_empty(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test error handling in claim type extraction."""
        mock_client.chat_completion.side_effect = Exception("API error")

        content = "Content"
        metadata = {"title": "Test"}

        result = extractor.extract_claim_types(content, metadata)

        assert result["facts"] == []
        assert result["opinions"] == []
        assert result["instructions"] == []

    def test_extract_claim_types_filters_invalid_types(
        self, extractor: ClaimsExtractor, mock_client: Mock
    ):
        """Test that non-list types in response are filtered."""
        mock_client.chat_completion.return_value = """{
            "facts": ["Fact 1", 123, null],
            "opinions": "This is wrong format",
            "instructions": ["Step 1"]
        }"""

        content = "Content"
        metadata = {"title": "Test"}

        result = extractor.extract_claim_types(content, metadata)

        # Only string facts should be included
        assert result["facts"] == ["Fact 1"]
        # Invalid format for opinions should result in empty list
        assert result["opinions"] == []
        assert result["instructions"] == ["Step 1"]


class TestClaimModel:
    """Tests for the Claim dataclass."""

    def test_claim_creation(self):
        """Test basic claim creation."""
        claim = Claim(
            text="Python was released in 1991",
            source_ref="paragraph 1",
            confidence=0.95,
            page_id="tech-page",
            evidence="Historical record confirms this date",
        )

        assert claim.text == "Python was released in 1991"
        assert claim.source_ref == "paragraph 1"
        assert claim.confidence == 0.95
        assert claim.page_id == "tech-page"
        assert claim.evidence == "Historical record confirms this date"

    def test_claim_defaults(self):
        """Test claim defaults."""
        claim = Claim(
            text="Test claim",
            source_ref="section 1",
            confidence=0.8,
            page_id="page1",
        )

        assert claim.evidence is None
        assert claim.temporal_context is None
        assert claim.qualifiers == []

    def test_claim_with_qualifiers(self):
        """Test claim with qualifiers."""
        claim = Claim(
            text="Coffee contains caffeine",
            source_ref="section 1",
            confidence=0.9,
            page_id="page1",
            qualifiers=["in most varieties", "typically"],
        )

        assert claim.qualifiers == ["in most varieties", "typically"]

    def test_claim_to_dict(self):
        """Test converting claim to dictionary."""
        claim = Claim(
            text="Test claim",
            source_ref="section 1",
            confidence=0.85,
            page_id="page1",
            evidence="Some evidence",
            temporal_context="2024",
            qualifiers=["qualifier1"],
        )

        claim_dict = claim.to_dict()

        assert claim_dict["text"] == "Test claim"
        assert claim_dict["source_ref"] == "section 1"
        assert claim_dict["confidence"] == 0.85
        assert claim_dict["page_id"] == "page1"
        assert claim_dict["evidence"] == "Some evidence"
        assert claim_dict["temporal_context"] == "2024"
        assert claim_dict["qualifiers"] == ["qualifier1"]

    def test_claim_from_dict(self):
        """Test creating claim from dictionary."""
        data = {
            "text": "Test claim",
            "source_ref": "section 1",
            "confidence": 0.9,
            "page_id": "page1",
            "evidence": "Evidence text",
            "temporal_context": "2024",
            "qualifiers": ["q1", "q2"],
        }

        claim = Claim.from_dict(data)

        assert claim.text == "Test claim"
        assert claim.source_ref == "section 1"
        assert claim.confidence == 0.9
        assert claim.page_id == "page1"
        assert claim.evidence == "Evidence text"
        assert claim.temporal_context == "2024"
        assert claim.qualifiers == ["q1", "q2"]

    def test_claim_from_dict_minimal(self):
        """Test creating claim from minimal dictionary."""
        data = {
            "text": "Test claim",
            "source_ref": "section 1",
            "confidence": 0.8,
            "page_id": "page1",
        }

        claim = Claim.from_dict(data)

        assert claim.text == "Test claim"
        assert claim.evidence is None
        assert claim.temporal_context is None
        assert claim.qualifiers == []

    def test_claim_roundtrip(self):
        """Test claim serialization roundtrip."""
        original = Claim(
            text="Test claim",
            source_ref="section 1",
            confidence=0.85,
            page_id="page1",
            evidence="Evidence",
            temporal_context="2024",
            qualifiers=["q1"],
        )

        # Convert to dict and back
        claim_dict = original.to_dict()
        restored = Claim.from_dict(claim_dict)

        assert restored.text == original.text
        assert restored.source_ref == original.source_ref
        assert restored.confidence == original.confidence
        assert restored.page_id == original.page_id
        assert restored.evidence == original.evidence
        assert restored.temporal_context == original.temporal_context
        assert restored.qualifiers == original.qualifiers
