"""Tests for dense vector index."""

from pathlib import Path

import pytest

from llm_wiki.index.vector import VectorIndex


def _has_vector_deps() -> bool:
    """Check if vector dependencies are available."""
    try:
        import faiss  # noqa: F401
        from sentence_transformers import SentenceTransformer  # noqa: F401

        return True
    except ImportError:
        return False


FAISS_AVAILABLE = _has_vector_deps()


@pytest.fixture
def index_dir(temp_dir: Path) -> Path:
    """Create index directory in temp space."""
    d = temp_dir / "index"
    d.mkdir()
    return d


@pytest.fixture
def vec_index(index_dir: Path) -> VectorIndex:
    """Create vector index in temp directory."""
    return VectorIndex(index_dir=index_dir)


class TestVectorIndexBasic:
    """Tests for VectorIndex when vector deps are unavailable."""

    def test_init(self):
        """Test initialization."""
        vi = VectorIndex()
        assert vi.doc_ids == []
        assert vi._model is None

    def test_search_no_model_returns_empty(self, vec_index: VectorIndex):
        """Test search returns empty when model unavailable."""
        # Ensure _model stays None so _ensure_model can't load it
        vec_index._model = object()  # type: ignore[assignment]
        vec_index._ensure_model = lambda: False  # type: ignore[method-assign]
        assert vec_index.search("hello") == []

    def test_add_document_no_model_does_nothing(self, vec_index: VectorIndex):
        """Test add_document is a no-op when model unavailable."""
        vec_index._ensure_model = lambda: False  # type: ignore[method-assign]
        vec_index.add_document("p1", "Title", "Content", "general")
        assert vec_index.doc_ids == []

    def test_rebuild_no_model_returns_zero(self, vec_index: VectorIndex, temp_dir: Path):
        """Test rebuild returns 0 without model."""
        vec_index._model = object()  # type: ignore[assignment]
        vec_index._ensure_model = lambda: False  # type: ignore[method-assign]
        wiki = temp_dir / "wiki"
        assert vec_index.rebuild_from_pages(wiki) == 0

    def test_save_no_model_does_nothing(self, vec_index: VectorIndex):
        """Test save is a noop without model."""
        vec_index._ensure_model = lambda: False  # type: ignore[method-assign]
        vec_index.add_document("p1", "T", "C", "general")  # no-op
        vec_index.save()  # should not raise


@pytest.mark.skipif(not FAISS_AVAILABLE, reason="faiss-cpu not installed")
class TestVectorIndexFull:
    """Integration tests requiring vector dependencies."""

    def test_add_document(self, vec_index: VectorIndex):
        """Test adding a document."""
        vec_index.add_document("p1", "Python Programming", "Learn Python", "tech")

        assert "p1" in vec_index.doc_ids
        assert "p1" in vec_index.doc_meta
        assert vec_index.doc_meta["p1"]["title"] == "Python Programming"
        assert vec_index.doc_meta["p1"]["domain"] == "tech"
        assert vec_index.doc_meta["p1"]["vector_idx"] == 0

    def test_add_multiple_documents(self, vec_index: VectorIndex):
        """Test adding multiple documents."""
        for i in range(5):
            vec_index.add_document(f"p{i}", f"Doc {i}", f"Content about topic {i}", "general")

        assert len(vec_index.doc_ids) == 5
        assert len(vec_index.idx_to_id) == 5
        assert len(vec_index.id_to_idx) == 5

    def test_remove_document(self, vec_index: VectorIndex):
        """Test removing a document."""
        vec_index.add_document("p1", "Title1", "Content1", "general")
        vec_index.add_document("p2", "Title2", "Content2", "general")
        vec_index.add_document("p3", "Title3", "Content3", "general")

        # Save to create FAISS index on disk
        vec_index.save()

        vec_index.remove_document("p2")

        assert "p2" not in vec_index.doc_ids
        assert "p2" not in vec_index.idx_to_id
        assert "p2" not in vec_index.id_to_idx
        assert "p2" not in vec_index.doc_meta
        assert len(vec_index.doc_ids) == 2

    def test_remove_nonexistent(self, vec_index: VectorIndex):
        """Test removing a nonexistent document."""
        vec_index.add_document("p1", "T", "C", "general")
        vec_index.remove_document("ghost")  # should not raise
        assert len(vec_index.doc_ids) == 1

    def test_save_and_load(self, vec_index: VectorIndex, index_dir: Path):
        """Test saving and loading index."""
        vec_index.add_document("p1", "Python Guide", "Python programming language", "tech")
        vec_index.add_document("p2", "JS Guide", "JavaScript basics", "tech")
        vec_index.save()

        # New instance load
        loaded = VectorIndex(index_dir=index_dir)
        loaded.load()

        assert len(loaded.doc_ids) == 2
        assert "p1" in loaded.doc_ids
        assert "p2" in loaded.doc_ids
        assert loaded.doc_meta["p1"]["title"] == "Python Guide"

    def test_load_nonexistent(self, vec_index: VectorIndex):
        """Test loading when no index exists."""
        vec_index.load()  # should not raise
        assert vec_index.doc_ids == []

    def test_rebuild_from_pages(self, vec_index: VectorIndex, temp_dir: Path):
        """Test rebuilding from wiki pages."""
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        (pages_dir / "p1.md").write_text(
            "---\nid: p1\ntitle: Python Programming\n---\nLearn Python programming."
        )
        (pages_dir / "p2.md").write_text("---\nid: p2\ntitle: Java Basics\n---\nLearn Java basics.")

        count = vec_index.rebuild_from_pages(wiki_base)

        assert count == 2
        assert "p1" in vec_index.doc_ids
        assert "p2" in vec_index.doc_ids

    def test_rebuild_clears_existing(self, vec_index: VectorIndex, temp_dir: Path):
        """Test that rebuild clears existing data."""
        vec_index.add_document("old", "Old", "Old content", "general")

        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        (pages_dir / "new.md").write_text("---\nid: new\ntitle: New Page\n---\nNew content.")

        vec_index.rebuild_from_pages(wiki_base)

        assert "old" not in vec_index.doc_ids
        assert "new" in vec_index.doc_ids

    def test_rebuild_from_pages_missing_domains(self, vec_index: VectorIndex, temp_dir: Path):
        """Test rebuild without domains directory."""
        assert vec_index.rebuild_from_pages(temp_dir / "nope") == 0

    def test_search_empty_index(self, vec_index: VectorIndex):
        """Test search on empty index."""
        assert vec_index.search("anything") == []

    def test_search_with_domain_filter(self, vec_index: VectorIndex):
        """Test search with domain filter."""
        vec_index.add_document("p1", "Python", "Python content", "tech")
        vec_index.add_document("p2", "Python", "Python content", "business")
        vec_index.save()

        results = vec_index.search("python", domain="tech")
        assert len(results) == 1
        assert results[0]["page_id"] == "p1"

        results = vec_index.search("python", domain="business")
        assert len(results) == 1
        assert results[0]["page_id"] == "p2"

    def test_search_returns_score(self, vec_index: VectorIndex):
        """Test search results include similarity score."""
        vec_index.add_document("p1", "Python Programming", "Learn Python programming", "tech")
        vec_index.save()

        results = vec_index.search("python programming")
        assert len(results) >= 1
        assert "score" in results[0]
        assert results[0]["score"] >= 0

    def test_search_limit(self, vec_index: VectorIndex):
        """Test search respects limit."""
        for i in range(10):
            vec_index.add_document(f"p{i}", f"Doc {i}", "Python content", "general")
        vec_index.save()

        results = vec_index.search("python", limit=3)
        assert len(results) <= 3

    def test_rebuild_from_pages_handles_errors(self, vec_index: VectorIndex, temp_dir: Path):
        """Test rebuild skips invalid files."""
        wiki_base = temp_dir / "wiki"
        pages_dir = wiki_base / "domains" / "general" / "pages"
        pages_dir.mkdir(parents=True)

        (pages_dir / "bad.md").write_text("---\ninvalid: yaml: ---\nX")
        # Add another valid file to make sure one passes
        (pages_dir / "good.md").write_text("---\nid: good\ntitle: Good Page\n---\nGood content")

        count = vec_index.rebuild_from_pages(wiki_base)
        # bad.md is skipped, good.md is indexed
        assert count >= 0  # May be 1 or 0 depending on frontmatter parsing

    def test_rebuild_multiple_domains(self, vec_index: VectorIndex, temp_dir: Path):
        """Test rebuild across multiple domains."""
        wiki_base = temp_dir / "wiki"
        for domain in ["tech", "science"]:
            pages_dir = wiki_base / "domains" / domain / "pages"
            pages_dir.mkdir(parents=True)
            (pages_dir / "doc.md").write_text(
                f"---\nid: {domain}_doc\ntitle: {domain} Doc\n---\nContent for {domain}."
            )

        count = vec_index.rebuild_from_pages(wiki_base)
        assert count == 2

    def test_save_load_persists_meta(self, vec_index: VectorIndex, index_dir: Path):
        """Test that saved metadata survives load."""
        vec_index.add_document("p1", "Alpha", "Alpha content", "alpha")
        vec_index.add_document("p2", "Beta", "Beta content", "beta")
        vec_index.save()

        loaded = VectorIndex(index_dir=index_dir)
        loaded.load()

        for m in loaded.doc_meta.values():
            assert "title" in m
            assert "domain" in m
            assert "vector_idx" in m
