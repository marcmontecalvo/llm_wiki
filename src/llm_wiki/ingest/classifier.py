"""Content-based domain classifier for inbox ingestion."""

import logging
import re
from pathlib import Path
from typing import Any

from llm_wiki.config.loader import load_config
from llm_wiki.extraction.service import ContentExtractor, ExtractionError
from llm_wiki.models.client import ModelClient, create_model_client
from llm_wiki.models.config import load_models_config
from llm_wiki.paths import resolve_wiki_base

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset(
    {
        "this",
        "that",
        "with",
        "from",
        "have",
        "will",
        "they",
        "been",
        "their",
        "there",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "these",
        "those",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "also",
        "am",
        "an",
        "and",
        "any",
        "are",
        "as",
        "at",
        "be",
        "because",
        "by",
        "can",
        "could",
        "did",
        "does",
        "doing",
        "down",
        "during",
        "each",
        "few",
        "for",
        "further",
        "get",
        "got",
        "he",
        "her",
        "here",
        "him",
        "his",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "just",
        "me",
        "might",
        "more",
        "most",
        "much",
        "must",
        "my",
        "no",
        "nor",
        "not",
        "now",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "our",
        "out",
        "over",
        "own",
        "s",
        "same",
        "she",
        "should",
        "so",
        "some",
        "such",
        "than",
        "the",
        "them",
        "then",
        "to",
        "together",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "we",
        "were",
        "why",
        "would",
        "you",
        "your",
    }
)


def _tokenize(text: str) -> list[str]:
    """Lowercase word tokens, filtering stopwords."""
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    return [w for w in words if w not in _STOPWORDS]


class Classifier:
    """Classifies content into domains using LLM or keyword heuristics."""

    def __init__(
        self,
        config_dir: Path | None = None,
        wiki_base: Path | None = None,
        client: ModelClient | None = None,
    ):
        self.config_dir = config_dir or Path("config")
        self.wiki_base = resolve_wiki_base(wiki_base)

        self._config = load_config(self.config_dir)
        self._domains = self._config.domains.domains
        self._domain_info = {
            d.id: {"title": d.title, "description": d.description} for d in self._domains
        }
        self._valid_domain_ids = {d.id for d in self._domains}

        self._content_extractor: ContentExtractor | None = None
        self._llm_available = False

        if client is not None:
            self._client = client
            self._llm_available = True
            self._content_extractor = ContentExtractor(client, self.config_dir)
            return

        try:
            models_config = load_models_config(self.config_dir / "models.yaml")
            provider_config = models_config.get_provider("extraction")
            if provider_config.model == "CHANGE_ME":
                logger.debug("LLM extraction model not configured, using heuristics")
                return
            self._client = create_model_client(provider_config)
            self._llm_available = True
            self._content_extractor = ContentExtractor(
                client=self._client, config_dir=self.config_dir
            )
        except FileNotFoundError:
            logger.debug("models.yaml not found, using heuristics")
            return
        except Exception as exc:
            logger.debug("LLM client initialization failed (%s), using heuristics", exc)
            return

    def classify(self, content: str, metadata: dict[str, Any]) -> str:
        """Determine the domain for the given content.

        Precedence:
        1. Explicit domain in metadata (frontmatter override)
        2. LLM-based classification (if available)
        3. Keyword heuristic fallback

        Args:
            content: Normalized markdown body content
            metadata: Extracted metadata from the adapter

        Returns:
            Domain ID string
        """
        # Explicit frontmatter override
        explicit_domain = metadata.get("domain")
        if explicit_domain and explicit_domain in self._valid_domain_ids:
            return str(explicit_domain)

        if self._llm_available and self._content_extractor is not None:
            return self._classify_with_llm(content, metadata)

        return self._classify_with_heuristics(content, metadata)

    def _classify_with_llm(self, content: str, metadata: dict[str, Any]) -> str:
        """Use LLM to determine the best matching domain."""
        title = metadata.get("title", "Untitled")
        domain_list = "\n".join(f"- {d.id}: {d.title} ({d.description})" for d in self._domains)

        prompt = (
            f"Given the following domains, which one best fits this content?\n\n"
            f"Domains:\n{domain_list}\n\n"
            f"Title: {title}\n"
            f"Content preview:\n{content[:1500]}\n\n"
            f"Respond with ONLY the domain ID (e.g. homelab, general, personal, "
            f"vulpine-solutions, home-assistant).\n"
            f"Do not include any other text."
        )

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self._client.chat_completion(messages).strip().lower()

            # Strip any surrounding quotes or whitespace
            response = response.strip("'\" ")

            if response in self._valid_domain_ids:
                return response

            logger.warning(
                "LLM returned unexpected domain '%s', defaulting to heuristics", response
            )
            return self._classify_with_heuristics(content, metadata)

        except ExtractionError as exc:
            logger.warning("LLM classification failed (%s), using heuristics", exc)
            return self._classify_with_heuristics(content, metadata)
        except Exception as exc:
            logger.warning("LLM classification failed (%s), using heuristics", exc)
            return self._classify_with_heuristics(content, metadata)

    def _classify_with_heuristics(self, content: str, metadata: dict[str, Any]) -> str:
        """Classify content by keyword overlap with domain descriptions.

        Uses BM25-style scoring: prefers tokens that appear many times
        in the content while being rare across all domain descriptions.
        """
        content_tokens = _tokenize(content)
        if not content_tokens:
            return self._second_best_domain()

        # Build domain index: domain_id -> set of relevant tokens from description
        domain_doc_tokens: dict[str, set[str]] = {}
        for did, info in self._domain_info.items():
            domain_doc_tokens[did] = set(_tokenize(f"{info['title']} {info['description']}"))

        # Compute term frequency in content
        from collections import Counter

        content_freq = Counter(content_tokens)
        content_len = len(content_tokens)

        # Score each domain
        scores: dict[str, float] = {}
        for did, d_tokens in domain_doc_tokens.items():
            if not d_tokens:
                scores[did] = 0.0
                continue
            # BM25-style: sum of term freq normalized by content length
            relevance = sum(content_freq[t] / content_len for t in d_tokens if t in content_freq)
            # Normalize by domain size to penalize longer descriptions
            relevance /= len(d_tokens)
            scores[did] = relevance

        best_domain = max(scores, key=lambda k: scores[k])
        best_score = scores[best_domain]

        # Require a minimum relevance threshold before assigning to a specific domain
        # A single keyword is not enough — need combined signal
        if best_score >= 0.02:
            return best_domain

        return self._second_best_domain()

    def _second_best_domain(self) -> str:
        """Return a safe fallback domain."""
        # Return 'general' if it exists, otherwise first domain
        if "general" in self._valid_domain_ids:
            return "general"
        if self._domains:
            return self._domains[0].id
        return "general"
