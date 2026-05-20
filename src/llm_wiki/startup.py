"""Daemon startup checks: inbox recovery + index integrity."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# These 4 JSON indexes are always required
_REQUIRED_INDEX_FILES = [
    "index/fulltext.json",
    "index/metadata.json",
    "index/backlinks.json",
    "index/edges.json",
]
# Vector index files — only checked when vector_search is enabled
_VECTOR_INDEX_FILES = [
    "index/vector_index.faiss",
    "index/vector_meta.json",
]


def check_index_integrity(wiki_base: Path, check_vector: bool = True) -> list[str]:
    """Return list of missing or zero-byte index file paths relative to wiki_base.

    Existence + non-empty check only — no parsing.

    Args:
        wiki_base: Base wiki directory path.
        check_vector: Whether to also check vector index files.

    Returns:
        List of relative paths to missing or corrupt index files.
    """
    files_to_check = list(_REQUIRED_INDEX_FILES)
    if check_vector:
        files_to_check.extend(_VECTOR_INDEX_FILES)

    corrupt = []
    for rel_path in files_to_check:
        path = wiki_base / rel_path
        if not path.exists() or path.stat().st_size == 0:
            corrupt.append(rel_path)
            logger.warning("Index integrity check failed: %s", rel_path)
    return corrupt
