"""Tests for startup module."""

from pathlib import Path

from llm_wiki.startup import check_index_integrity


class TestCheckIndexIntegrity:
    """Tests for check_index_integrity."""

    def test_passes_with_all_required_files(self, wiki_root: Path):
        """No corruption when all index files exist and are non-empty."""
        index_dir = wiki_root / "index"
        index_dir.mkdir(exist_ok=True)
        for name in ["fulltext.json", "metadata.json", "backlinks.json", "graph_edges.json"]:
            (index_dir / name).write_text("{}", encoding="utf-8")
        result = check_index_integrity(wiki_root, check_vector=False)
        assert result == []

    def test_detects_missing_file(self, wiki_root: Path):
        """Missing required index file is reported."""
        index_dir = wiki_root / "index"
        index_dir.mkdir(exist_ok=True)
        for name in ["metadata.json", "backlinks.json", "graph_edges.json"]:
            (index_dir / name).write_text("{}", encoding="utf-8")
        result = check_index_integrity(wiki_root, check_vector=False)
        assert "index/fulltext.json" in result

    def test_detects_zero_byte_file(self, wiki_root: Path):
        """Zero-byte index file is reported as corrupt."""
        index_dir = wiki_root / "index"
        index_dir.mkdir(exist_ok=True)
        for name in ["fulltext.json", "metadata.json", "backlinks.json", "graph_edges.json"]:
            (index_dir / name).write_text("" if name == "fulltext.json" else "{}", encoding="utf-8")
        result = check_index_integrity(wiki_root, check_vector=False)
        assert "index/fulltext.json" in result

    def test_detects_missing_vector_files(self, wiki_root: Path):
        """Vector index files are reported missing when check_vector=True."""
        index_dir = wiki_root / "index"
        index_dir.mkdir(exist_ok=True)
        for name in ["fulltext.json", "metadata.json", "backlinks.json", "graph_edges.json"]:
            (index_dir / name).write_text("{}", encoding="utf-8")
        result = check_index_integrity(wiki_root, check_vector=True)
        assert "index/vector_index.faiss" in result
        assert "index/vector_meta.json" in result

    def test_no_missing_vector_files_when_disabled(self, wiki_root: Path):
        """Vector index files are skipped when check_vector=False."""
        index_dir = wiki_root / "index"
        index_dir.mkdir(exist_ok=True)
        for name in ["fulltext.json", "metadata.json", "backlinks.json", "graph_edges.json"]:
            (index_dir / name).write_text("{}", encoding="utf-8")
        result = check_index_integrity(wiki_root, check_vector=False)
        assert all("vector" not in item for item in result)
