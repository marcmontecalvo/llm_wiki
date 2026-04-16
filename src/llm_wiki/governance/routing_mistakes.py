"""Routing mistake detection for wiki pages."""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)

# Keywords derived from each domain's description (used for tag/content scoring).
# Keys are domain IDs; values are sets of lowercase keyword tokens.
_DOMAIN_KEYWORDS: dict[str, set[str]] = {
    "vulpine-solutions": {
        "msp",
        "operations",
        "sales",
        "security",
        "client",
        "delivery",
        "managed",
        "service",
        "provider",
        "business",
        "contract",
        "invoice",
        "ticket",
        "sla",
    },
    "home-assistant": {
        "automation",
        "voice",
        "assistant",
        "esp32",
        "ai",
        "sensor",
        "sensors",
        "home",
        "iot",
        "smart",
        "mqtt",
        "zigbee",
        "zwave",
        "local",
        "ha",
        "hass",
    },
    "homelab": {
        "proxmox",
        "k3s",
        "kubernetes",
        "storage",
        "networking",
        "network",
        "gpu",
        "gpus",
        "server",
        "services",
        "docker",
        "vm",
        "nas",
        "pve",
        "cluster",
        "node",
    },
    "personal": {
        "family",
        "logistics",
        "hobbies",
        "hobby",
        "plans",
        "notes",
        "personal",
        "diary",
        "todo",
        "travel",
        "health",
        "finance",
        "budget",
    },
    "general": {
        "general",
        "misc",
        "miscellaneous",
        "unclassified",
        "draft",
        "scratch",
    },
}


@dataclass
class RoutingDecision:
    """Represents a routing decision for a page."""

    page_id: str
    chosen_domain: str
    confidence: float
    alternative_domains: list[str] = field(default_factory=list)
    routing_method: str = "unknown"  # explicit, tag_match, link_affinity, content_keywords


@dataclass
class RoutingMistake:
    """Represents a detected routing mistake for a page."""

    page_id: str
    current_domain: str
    suggested_domain: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "pending"  # pending, confirmed, dismissed, corrected

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "page_id": self.page_id,
            "current_domain": self.current_domain,
            "suggested_domain": self.suggested_domain,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "detected_at": self.detected_at,
            "status": self.status,
        }


@dataclass
class RoutingMistakeReport:
    """Report of detected routing mistakes."""

    total_pages_scanned: int
    total_mistakes: int
    high_confidence: list[RoutingMistake] = field(default_factory=list)
    medium_confidence: list[RoutingMistake] = field(default_factory=list)
    low_confidence: list[RoutingMistake] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class RoutingMistakeDetector:
    """Detects pages that may be routed to the wrong domain.

    Detection uses three heuristics, combined into a confidence score:

    1. **Explicit mismatch** — the page's ``domain`` frontmatter key specifies a
       domain that differs from the directory it currently lives in.
    2. **Tag analysis** — the page's ``tags`` field is scored against keyword
       sets associated with each domain.  A strong overlap with a different
       domain raises the confidence.
    3. **Link affinity** — the ratio of wiki-links that point to pages in
       another domain.  When most outgoing links target a single foreign domain
       that domain becomes the suggested one.

    Args:
        min_confidence: Minimum confidence (0.0–1.0) to include a mistake in
                        the report.  Defaults to ``0.3``.
        domain_keywords: Override the built-in keyword map for testing.
    """

    def __init__(
        self,
        min_confidence: float = 0.3,
        wiki_base: Path | None = None,
        domain_keywords: dict[str, set[str]] | None = None,
    ):
        self.min_confidence = min_confidence
        self.wiki_base = wiki_base
        self._domain_keywords = domain_keywords if domain_keywords is not None else _DOMAIN_KEYWORDS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_all_pages(self, wiki_base: Path | None = None) -> RoutingMistakeReport:
        """Scan all wiki pages and return a routing mistake report.

        Args:
            wiki_base: Base wiki directory (defaults to instance wiki_base or
                       ``wiki_system/``).

        Returns:
            :class:`RoutingMistakeReport` with detected mistakes.
        """
        if wiki_base is None:
            wiki_base = self.wiki_base
        if wiki_base is None:
            wiki_base = Path("wiki_system")

        domains_dir = wiki_base / "domains"
        if not domains_dir.exists():
            logger.warning(f"Domains directory not found: {domains_dir}")
            return RoutingMistakeReport(total_pages_scanned=0, total_mistakes=0)

        # Build a map of page_id -> domain_id by scanning all pages directories
        page_domain_map = self._build_page_domain_map(domains_dir)

        all_mistakes: list[RoutingMistake] = []
        total_pages = 0

        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue

            current_domain = domain_dir.name

            for page_file in pages_dir.glob("*.md"):
                total_pages += 1
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, body = parse_frontmatter(content)
                    page_id = metadata.get("id", page_file.stem)

                    mistake = self._analyze_page(
                        page_id, current_domain, metadata, body, page_domain_map
                    )
                    if mistake is not None and mistake.confidence >= self.min_confidence:
                        all_mistakes.append(mistake)
                except Exception as e:
                    logger.error(f"Failed to analyze {page_file}: {e}")

        # Build report
        report = RoutingMistakeReport(
            total_pages_scanned=total_pages,
            total_mistakes=len(all_mistakes),
        )
        for mistake in all_mistakes:
            if mistake.confidence >= 0.7:
                report.high_confidence.append(mistake)
            elif mistake.confidence >= 0.4:
                report.medium_confidence.append(mistake)
            else:
                report.low_confidence.append(mistake)

        logger.info(
            f"Routing analysis: {total_pages} pages scanned, "
            f"{len(all_mistakes)} potential mistakes found"
        )
        return report

    def analyze_page(
        self,
        page_id: str,
        current_domain: str,
        metadata: dict[str, Any],
        body: str,
        page_domain_map: dict[str, str] | None = None,
    ) -> RoutingMistake | None:
        """Analyze a single page for routing mistakes.

        Args:
            page_id: Page identifier.
            current_domain: Domain the page currently lives in.
            metadata: Parsed frontmatter dict.
            body: Page body text.
            page_domain_map: Optional mapping of page_id -> domain_id; used for
                             link-affinity analysis.  Pass ``None`` to skip
                             link-affinity scoring.

        Returns:
            :class:`RoutingMistake` if a mistake is detected above the
            configured threshold, else ``None``.
        """
        return self._analyze_page(page_id, current_domain, metadata, body, page_domain_map or {})

    def generate_report(self, report: RoutingMistakeReport, output_path: Path) -> Path:
        """Write a markdown report to *output_path*.

        Args:
            report: :class:`RoutingMistakeReport` to serialize.
            output_path: Destination file path.

        Returns:
            The path that was written.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            "# Routing Mistake Detection Report",
            f"Generated: {report.timestamp}",
            "",
            "## Summary",
            f"- Pages scanned: {report.total_pages_scanned}",
            f"- Total potential mistakes: {report.total_mistakes}",
            f"- High confidence (>= 0.7): {len(report.high_confidence)}",
            f"- Medium confidence (0.4–0.7): {len(report.medium_confidence)}",
            f"- Low confidence (0.3–0.4): {len(report.low_confidence)}",
            "",
        ]

        def _section(title: str, mistakes: list[RoutingMistake]) -> None:
            if not mistakes:
                return
            lines.append(f"## {title}")
            lines.append("")
            for m in sorted(mistakes, key=lambda x: x.confidence, reverse=True):
                lines.extend(self._format_mistake(m))
                lines.append("")

        _section("High Confidence Mistakes (>= 0.70)", report.high_confidence)
        _section("Medium Confidence Mistakes (0.40–0.70)", report.medium_confidence)
        _section("Low Confidence Mistakes (0.30–0.40)", report.low_confidence)

        output_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Routing mistake report written to {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_page_domain_map(self, domains_dir: Path) -> dict[str, str]:
        """Return a mapping of page_id -> domain_id for all pages files."""
        mapping: dict[str, str] = {}
        for domain_dir in domains_dir.iterdir():
            if not domain_dir.is_dir():
                continue
            pages_dir = domain_dir / "pages"
            if not pages_dir.exists():
                continue
            for page_file in pages_dir.glob("*.md"):
                try:
                    content = page_file.read_text(encoding="utf-8")
                    metadata, _ = parse_frontmatter(content)
                    page_id = metadata.get("id", page_file.stem)
                    mapping[page_id] = domain_dir.name
                except Exception:
                    # Use stem as fallback page_id
                    mapping[page_file.stem] = domain_dir.name
        return mapping

    def _analyze_page(
        self,
        page_id: str,
        current_domain: str,
        metadata: dict[str, Any],
        body: str,
        page_domain_map: dict[str, str],
    ) -> RoutingMistake | None:
        """Run all heuristics on one page and return a mistake or None."""
        reasons: list[str] = []
        domain_scores: dict[str, float] = {}

        # 1. Explicit frontmatter domain mismatch
        explicit_domain = metadata.get("domain", "")
        if explicit_domain and explicit_domain != current_domain:
            _add_score(domain_scores, explicit_domain, 0.9)
            reasons.append(
                f"Frontmatter specifies domain={explicit_domain!r} "
                f"but page lives in {current_domain!r}"
            )

        # 2. Tag-based analysis
        tags = metadata.get("tags", []) or []
        if tags:
            tag_scores = self._score_tags(tags, current_domain)
            for domain, score in tag_scores.items():
                if score > 0:
                    _add_score(domain_scores, domain, score * 0.5)
                    if score >= 0.5:
                        matching_tags = self._matching_tags(tags, domain)
                        reasons.append(
                            f"Tags suggest {domain!r}: {', '.join(sorted(matching_tags)[:5])}"
                        )

        # 3. Link-affinity analysis
        if page_domain_map:
            link_domain = self._score_link_affinity(body, current_domain, page_domain_map)
            if link_domain is not None:
                target_domain, ratio = link_domain
                _add_score(domain_scores, target_domain, ratio * 0.4)
                reasons.append(f"{ratio:.0%} of outgoing links point to {target_domain!r} pages")

        if not domain_scores:
            return None

        # Pick the best non-current domain
        best_domain = max(domain_scores, key=lambda d: domain_scores[d])
        confidence = min(1.0, domain_scores[best_domain])

        if best_domain == current_domain or confidence < self.min_confidence:
            return None

        return RoutingMistake(
            page_id=page_id,
            current_domain=current_domain,
            suggested_domain=best_domain,
            confidence=confidence,
            reasons=reasons,
        )

    def _score_tags(self, tags: list[str], current_domain: str) -> dict[str, float]:
        """Return a score per domain based on tag overlap (excluding current)."""
        scores: dict[str, float] = {}
        norm_tags = {t.lower().strip() for t in tags if t}

        for domain, keywords in self._domain_keywords.items():
            if domain == current_domain:
                continue
            overlap = norm_tags & keywords
            if overlap:
                scores[domain] = len(overlap) / len(norm_tags)

        return scores

    def _matching_tags(self, tags: list[str], domain: str) -> set[str]:
        """Return the subset of tags that match *domain*'s keyword set."""
        norm_tags = {t.lower().strip() for t in tags if t}
        keywords = self._domain_keywords.get(domain, set())
        return norm_tags & keywords

    def _score_link_affinity(
        self,
        body: str,
        current_domain: str,
        page_domain_map: dict[str, str],
    ) -> tuple[str, float] | None:
        """Return (best_foreign_domain, ratio) if a clear link-affinity signal exists.

        Returns ``None`` when there are fewer than 2 resolvable links or no
        foreign-domain majority.
        """
        links = re.findall(r"\[\[([^\]]+)\]\]", body)
        if not links:
            return None

        foreign_counts: dict[str, int] = {}
        resolvable = 0

        for link in links:
            target = link.strip()
            domain = page_domain_map.get(target)
            if domain is None:
                continue
            resolvable += 1
            if domain != current_domain:
                foreign_counts[domain] = foreign_counts.get(domain, 0) + 1

        if resolvable < 2:
            return None

        if not foreign_counts:
            return None

        best = max(foreign_counts, key=lambda d: foreign_counts[d])
        ratio = foreign_counts[best] / resolvable

        # Require a clear majority (> 60%) before flagging
        if ratio < 0.6:
            return None

        return best, ratio

    def _format_mistake(self, mistake: RoutingMistake) -> list[str]:
        return [
            f"### {mistake.page_id}",
            "",
            f"**Current domain**: {mistake.current_domain}",
            f"**Suggested domain**: {mistake.suggested_domain}",
            f"**Confidence**: {mistake.confidence:.2f}",
            f"**Status**: {mistake.status}",
            "",
            "**Reasons**:",
            *[f"- {r}" for r in mistake.reasons],
        ]


def _add_score(scores: dict[str, float], domain: str, value: float) -> None:
    """Accumulate a domain score, capping at 1.0."""
    scores[domain] = min(1.0, scores.get(domain, 0.0) + value)
