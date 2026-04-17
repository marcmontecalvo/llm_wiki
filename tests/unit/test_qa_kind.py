"""Tests for the qa PageKind and QAFrontmatter schema."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from llm_wiki.models.page import QAFrontmatter, create_frontmatter


class TestQAFrontmatter:
    """Tests for QAFrontmatter validation."""

    def _base_kwargs(self):
        return {
            "id": "qa-how-to-x",
            "title": "How to X",
            "domain": "general",
            "updated_at": datetime.now(UTC),
            "question": "How do I X?",
            "answer": "Do Y.",
        }

    def test_valid_qa_frontmatter(self):
        """A valid QA frontmatter object can be created."""
        fm = QAFrontmatter(**self._base_kwargs())
        assert fm.kind == "qa"
        assert fm.question == "How do I X?"
        assert fm.answer == "Do Y."
        assert fm.related_pages == []

    def test_rejects_empty_question(self):
        """Empty question fails validation."""
        kwargs = self._base_kwargs()
        kwargs["question"] = "   "
        with pytest.raises(ValidationError):
            QAFrontmatter(**kwargs)

    def test_rejects_empty_answer(self):
        """Empty answer fails validation."""
        kwargs = self._base_kwargs()
        kwargs["answer"] = ""
        with pytest.raises(ValidationError):
            QAFrontmatter(**kwargs)

    def test_related_pages_list(self):
        """related_pages defaults to empty list and accepts values."""
        kwargs = self._base_kwargs()
        kwargs["related_pages"] = ["concept-a", "entity-b"]
        fm = QAFrontmatter(**kwargs)
        assert fm.related_pages == ["concept-a", "entity-b"]


class TestCreateFrontmatterQA:
    """Tests for the factory routing qa kind to QAFrontmatter."""

    def test_factory_produces_qa(self):
        """create_frontmatter('qa', ...) returns a QAFrontmatter."""
        fm = create_frontmatter(
            "qa",
            id="qa-foo",
            title="Foo?",
            domain="general",
            updated_at=datetime.now(UTC),
            question="Foo?",
            answer="Bar.",
        )
        assert isinstance(fm, QAFrontmatter)
        assert fm.kind == "qa"
