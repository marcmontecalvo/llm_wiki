"""Dense vector index for semantic search."""

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class VectorIndex:
    """FAISS-based vector index for semantic/dense retrieval."""

    def __init__(self, index_dir: Path | None = None):
        """Initialize vector index.

        Args:
            index_dir: Directory to store index (defaults to wiki_system/index)
        """
        self.index_dir = index_dir or Path("wiki_system/index")
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.doc_ids: list[str] = []
        self.idx_to_id: dict[int, str] = {}
        self.id_to_idx: dict[str, int] = {}
        self.doc_meta: dict[str, dict[str, Any]] = {}
        self._embedded_texts: dict[str, str] = {}  # page_id -> text for re-embedding

        # Lazy loaded to avoid hard dependency
        self._model: Any | None = None

    def _ensure_model(self) -> bool:
        """Load sentence-transformers model if available.

        Returns:
            True if model is available, False otherwise.
        """
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Loaded sentence-transformers model (all-MiniLM-L6-v2)")
                return True
            except ImportError:
                logger.debug(
                    "sentence-transformers not installed; "
                    "vector search disabled. Install with: pip install llm-wiki[vector]"
                )
                self._model = None  # type: ignore[assignment]
                return False
        return True  # Already loaded successfully

    @staticmethod
    def _clean_for_embedding(text: str) -> str:
        """Strip markdown syntax and normalize whitespace for embedding."""
        text = re.sub(r"[#*`_~\[\]]", "", text)
        text = re.sub(r"^[\-\*]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r">\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n{2,}", "\n", text).strip()
        return text

    def _rebuild_idx_maps(self) -> None:
        """Rebuild idx_to_id and id_to_idx from doc_ids order."""
        self.idx_to_id.clear()
        self.id_to_idx.clear()
        for i, pid in enumerate(self.doc_ids):
            self.idx_to_id[i] = pid
            self.id_to_idx[pid] = i

    def add_document(self, page_id: str, title: str, content: str, domain: str) -> None:
        """Add or update a document in the vector index.

        Args:
            page_id: Page identifier.
            title: Page title.
            content: Page content (markdown).
            domain: Domain identifier.
        """
        if not self._ensure_model():
            return

        import numpy as np

        model = self._model  # type: ignore[union-attr]
        text = self._clean_for_embedding(f"{title} {content}")
        embedding = model.encode(  # type: ignore[union-attr]
            text,
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        embedding = np.asarray(embedding, dtype="float32").reshape(1, -1)

        self.doc_ids.append(page_id)
        self.doc_meta[page_id] = {
            "title": title,
            "domain": domain,
            "vector_idx": len(self.doc_ids) - 1,
        }
        self._embedded_texts[page_id] = text
        self._rebuild_idx_maps()

    def remove_document_in_memory(self, page_id: str) -> None:
        """Remove a document from the in-memory vector index only.

        Does NOT persist to disk — caller must save under lock.

        Args:
            page_id: Page identifier.
        """
        if page_id not in self.id_to_idx:
            return

        # Remove from in-memory state
        self.doc_meta.pop(page_id, None)
        self._embedded_texts.pop(page_id, None)
        self.doc_ids = [pid for pid in self.doc_ids if pid != page_id]
        self._rebuild_idx_maps()

    def remove_document(self, page_id: str) -> None:
        """Remove document and persist immediately. For direct callers outside WikiQuery."""
        self.remove_document_in_memory(page_id)
        self._save_index_to_disk()

    def search(
        self,
        query: str,
        domain: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for semantically similar documents.

        Args:
            query: Search query string.
            domain: Optional domain to scope search.
            limit: Maximum results to return.

        Returns:
            List of results with page_id, title, domain, score.
        """
        if not self._ensure_model():
            return []

        import numpy as np

        clean_query = self._clean_for_embedding(query)
        query_vec = self._model.encode(  # type: ignore[union-attr]
            clean_query,
            batch_size=1,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        query_vec = np.asarray(query_vec, dtype="float32").reshape(1, -1)

        try:
            index = self._load_faiss_index()
            if index is None:
                return []

            n_results = min(limit * 2, len(self.doc_ids))
            if n_results < 1:
                return []
            scores, indices = index.search(query_vec, n_results)

            results = []
            for s, i in zip(scores[0], indices[0], strict=False):
                if i < 0 or i >= len(self.doc_ids):
                    continue
                page_id = self.doc_ids[i]
                meta = self.doc_meta.get(page_id, {})
                if domain and meta.get("domain") != domain:
                    continue
                results.append(
                    {
                        "page_id": page_id,
                        "title": meta.get("title", page_id),
                        "domain": meta.get("domain", "general"),
                        "score": float(s),
                    }
                )

            return results[:limit]

        except Exception as e:
            logger.error(f"Failed to search vector index: {e}")
            return []

    def _load_faiss_index(self) -> Any | None:
        """Load FAISS index from disk.

        Returns:
            FAISS index or None if not available.
        """
        import faiss

        faiss_path = self.index_dir / "vector_index.faiss"
        if not faiss_path.exists():
            return None
        return faiss.read_index(str(faiss_path))

    def _save_index_to_disk(self) -> None:
        """Save current in-memory vectors + metadata to disk.

        Re-embeds all documents from stored clean text. If _model is
        unavailable the disk is left as-is and this returns silently.
        """
        import faiss
        import numpy as np

        if not self.doc_ids:
            # Remove stale files if present
            (self.index_dir / "vector_index.faiss").unlink(missing_ok=True)
            (self.index_dir / "vector_meta.json").unlink(missing_ok=True)
            return

        if self._model is None:
            logger.debug("Cannot persist vector index: model not loaded")
            return

        model = self._model  # type: ignore[union-attr]
        try:
            texts = [
                self.doc_meta.get(pid, {}).get("title", "")
                + " "
                + self._embedded_texts.get(pid, "")
                for pid in self.doc_ids
            ]
            texts = [self._clean_for_embedding(t) for t in texts]

            embeddings = model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            embeddings = np.asarray(embeddings, dtype="float32")

            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(embeddings)

            faiss_path = self.index_dir / "vector_index.faiss"
            tmp_faiss = str(faiss_path) + ".tmp"
            faiss.write_index(index, tmp_faiss)
            try:
                os.replace(tmp_faiss, faiss_path)
            except BaseException:
                os.unlink(tmp_faiss)
                raise
        except Exception as e:
            logger.error(f"Failed to save vector index: {e}")
            return

        meta_path = self.index_dir / "vector_meta.json"
        fd = tempfile.NamedTemporaryFile(
            "w", dir=self.index_dir, delete=False, suffix=".tmp", encoding="utf-8"
        )
        try:
            json.dump(self.doc_meta, fd, indent=2)
            fd.close()
            os.replace(fd.name, meta_path)
        except BaseException:
            fd.close()
            os.unlink(fd.name)
            raise

        logger.info(f"Saved vector index ({len(self.doc_ids)} documents)")

    def save(self) -> None:
        """Save index to disk atomically (tmp + os.replace)."""
        if not self._ensure_model():
            return

        if not self.doc_ids:
            logger.debug("No documents to save in vector index")
            return

        import faiss
        import numpy as np

        texts = [
            self.doc_meta.get(pid, {}).get("title", "") + " " + self._embedded_texts.get(pid, "")
            for pid in self.doc_ids
        ]
        texts = [self._clean_for_embedding(t) for t in texts]

        embeddings = self._model.encode(  # type: ignore[union-attr]
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        embeddings = np.asarray(embeddings, dtype="float32")

        index = faiss.IndexFlatL2(embeddings.shape[1])
        index.add(embeddings)

        faiss_path = self.index_dir / "vector_index.faiss"
        tmp_faiss = str(faiss_path) + ".tmp"
        faiss.write_index(index, tmp_faiss)
        try:
            os.replace(tmp_faiss, faiss_path)
        except BaseException:
            os.unlink(tmp_faiss)
            raise

        meta_path = self.index_dir / "vector_meta.json"
        fd = tempfile.NamedTemporaryFile(
            "w", dir=self.index_dir, delete=False, suffix=".tmp", encoding="utf-8"
        )
        try:
            json.dump(self.doc_meta, fd, indent=2)
            fd.close()
            os.replace(fd.name, meta_path)
        except BaseException:
            fd.close()
            os.unlink(fd.name)
            raise

        logger.info(f"Saved vector index ({len(self.doc_ids)} documents)")

    def load(self) -> None:
        """Load index from disk."""
        meta_path = self.index_dir / "vector_meta.json"
        if not meta_path.exists():
            logger.debug("No existing vector index found")
            return

        with meta_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)

        self.doc_ids.clear()
        self.idx_to_id.clear()
        self.id_to_idx.clear()
        self.doc_meta.clear()
        self._embedded_texts.clear()

        for page_id, m in meta.items():
            self.doc_ids.append(page_id)
            idx = m.get("vector_idx", len(self.doc_ids) - 1)
            self.idx_to_id[idx] = page_id
            self.id_to_idx[page_id] = idx
            self.doc_meta[page_id] = m

        logger.info(f"Loaded vector index ({len(self.doc_ids)} documents)")

    def rebuild_from_pages(
        self,
        wiki_base: Path | None = None,
    ) -> int:
        """Rebuild vector index from all wiki pages.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/).

        Returns:
            Number of documents indexed.
        """
        wiki_base = wiki_base or Path("wiki_system")
        if not self._ensure_model():
            logger.warning("Skipping vector rebuild: sentence-transformers not available")
            return 0

        self.doc_ids.clear()
        self.idx_to_id.clear()
        self.id_to_idx.clear()
        self.doc_meta.clear()
        self._embedded_texts.clear()

        from llm_wiki.utils.frontmatter import parse_frontmatter

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return 0

        pages: list[tuple[str, str, str, str]] = []
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            for page_file in pages_dir.glob("*.md"):
                try:
                    content_text = page_file.read_text(encoding="utf-8")
                    metadata, body = parse_frontmatter(content_text)
                    page_id = metadata.get("id", page_file.stem)
                    title = metadata.get("title", page_file.stem)
                    domain = metadata.get("domain", domain_dir.name)
                    pages.append((page_id, title, body, domain))
                except Exception as e:
                    logger.error(f"Failed to index {page_file}: {e}")

        if not pages:
            return 0

        import numpy as np

        texts = [
            self._clean_for_embedding(f"{title} {content}") for page_id, title, content, _ in pages
        ]

        embeddings = self._model.encode(  # type: ignore[union-attr]
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        embeddings = np.asarray(embeddings, dtype="float32")

        import faiss

        for idx, (page_id, title, _, domain) in enumerate(pages):
            self.doc_ids.append(page_id)
            self.idx_to_id[idx] = page_id
            self.id_to_idx[page_id] = idx
            self.doc_meta[page_id] = {
                "title": title,
                "domain": domain,
                "vector_idx": idx,
            }
            self._embedded_texts[page_id] = texts[idx]

        # Build FAISS index from embeddings
        index = faiss.IndexFlatL2(embeddings.shape[1])
        index.add(embeddings)

        faiss_path = self.index_dir / "vector_index.faiss"
        faiss.write_index(index, str(faiss_path))

        meta_path = self.index_dir / "vector_meta.json"
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(self.doc_meta, f, indent=2)

        logger.info(f"Saved vector index ({len(self.doc_ids)} documents)")
        return len(pages)
