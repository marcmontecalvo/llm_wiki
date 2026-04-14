"""Fulltext search indexer."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)


class FulltextIndex:
    """Simple inverted index for fulltext search."""

    def __init__(self, index_dir: Path | None = None):
        """Initialize fulltext index.

        Args:
            index_dir: Directory to store index (defaults to wiki_system/index)
        """
        self.index_dir = index_dir or Path("wiki_system/index")
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # word -> {page_id: count}
        self.inverted_index: dict[str, dict[str, int]] = {}
        # page_id -> {title, domain, word_count}
        self.documents: dict[str, dict[str, Any]] = {}

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into words.

        Args:
            text: Text to tokenize

        Returns:
            List of normalized words
        """
        # Convert to lowercase and extract words
        text = text.lower()
        words = re.findall(r"\b[a-z0-9]{2,}\b", text)
        return words

    def add_document(self, page_id: str, title: str, content: str, domain: str = "general") -> None:
        """Add or update a document in the index.

        Args:
            page_id: Page identifier
            title: Page title
            content: Page content (markdown)
            domain: Domain identifier
        """
        # Tokenize title and content
        title_words = self._tokenize(title)
        content_words = self._tokenize(content)

        # Title words weighted higher (appear 3x)
        all_words = title_words * 3 + content_words

        # Count word frequencies
        word_counts: dict[str, int] = {}
        for word in all_words:
            word_counts[word] = word_counts.get(word, 0) + 1

        # Update inverted index
        for word, count in word_counts.items():
            if word not in self.inverted_index:
                self.inverted_index[word] = {}
            self.inverted_index[word][page_id] = count

        # Store document metadata
        self.documents[page_id] = {
            "title": title,
            "domain": domain,
            "word_count": len(all_words),
        }

    def remove_document(self, page_id: str) -> None:
        """Remove a document from the index.

        Args:
            page_id: Page identifier
        """
        if page_id not in self.documents:
            return

        # Remove from inverted index
        for word_dict in self.inverted_index.values():
            word_dict.pop(page_id, None)

        # Remove document metadata
        del self.documents[page_id]

    def search(
        self, query: str, domain: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search for documents matching query.

        Args:
            query: Search query
            domain: Optional domain to scope search
            limit: Maximum results to return

        Returns:
            List of results with page_id, title, domain, score
        """
        # Tokenize query
        query_words = self._tokenize(query)
        if not query_words:
            return []

        # Calculate scores for each document
        scores: dict[str, float] = {}

        for word in query_words:
            if word not in self.inverted_index:
                continue

            # IDF: inverse document frequency
            num_docs_with_word = len(self.inverted_index[word])
            idf = 1.0 / (1.0 + num_docs_with_word)

            for page_id, count in self.inverted_index[word].items():
                # Skip if domain filter doesn't match
                if domain and self.documents[page_id]["domain"] != domain:
                    continue

                # TF: term frequency
                doc_word_count = self.documents[page_id]["word_count"]
                tf = count / max(doc_word_count, 1)

                # TF-IDF score
                score = tf * idf

                scores[page_id] = scores.get(page_id, 0.0) + score

        # Sort by score and return top results
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for page_id, score in sorted_results[:limit]:
            doc = self.documents[page_id]
            results.append(
                {
                    "page_id": page_id,
                    "title": doc["title"],
                    "domain": doc["domain"],
                    "score": score,
                }
            )

        return results

    def save(self) -> None:
        """Save index to disk."""
        index_file = self.index_dir / "fulltext.json"

        data = {
            "inverted_index": self.inverted_index,
            "documents": self.documents,
        }

        with index_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved fulltext index ({len(self.documents)} documents)")

    def load(self) -> None:
        """Load index from disk."""
        index_file = self.index_dir / "fulltext.json"

        if not index_file.exists():
            logger.info("No existing fulltext index found")
            return

        with index_file.open("r", encoding="utf-8") as f:
            data = json.load(f)

        self.inverted_index = data.get("inverted_index", {})
        self.documents = data.get("documents", {})

        logger.info(f"Loaded fulltext index ({len(self.documents)} documents)")

    def rebuild_from_pages(self, wiki_base: Path | None = None) -> int:
        """Rebuild index from all wiki pages.

        Args:
            wiki_base: Base wiki directory (defaults to wiki_system/)

        Returns:
            Number of documents indexed
        """
        wiki_base = wiki_base or Path("wiki_system")

        # Clear existing index
        self.inverted_index.clear()
        self.documents.clear()

        # Scan all domains
        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return 0

        count = 0
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue

            domain_id = domain_dir.name
            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            # Index all markdown files
            for page_file in pages_dir.glob("*.md"):
                try:
                    content_text = page_file.read_text(encoding="utf-8")
                    metadata, body = parse_frontmatter(content_text)

                    page_id = metadata.get("id", page_file.stem)
                    title = metadata.get("title", page_file.stem)

                    self.add_document(page_id, title, body, domain_id)
                    count += 1

                except Exception as e:
                    logger.error(f"Failed to index {page_file}: {e}")

        logger.info(f"Rebuilt fulltext index: {count} documents")
        return count
