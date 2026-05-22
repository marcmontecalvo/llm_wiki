"""Dashboard service — per-domain health computation.

Reads from existing index structures (metadata, changelog, jobs.json)
and returns derived dashboard data. Never writes new persistent state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from llm_wiki.api.models import (
    DashboardConfidenceDistribution,
    DashboardLastGovernanceRun,
    DashboardRecentChange,
    DashboardResponse,
)
from llm_wiki.changelog.log import ChangeLog
from llm_wiki.exceptions import DomainUnknownError
from llm_wiki.index.metadata import MetadataIndex

logger = logging.getLogger(__name__)

# Simple TTL cache for metadata index loads to avoid re-parsing on concurrent requests.
# Key: index directory path str, Value: (cache_time, MetadataIndex instance).
_metadata_cache: dict[str, tuple[float, MetadataIndex]] = {}
_METADATA_TTL_SECONDS = 5


def _get_cached_metadata(index_dir: Path) -> MetadataIndex:
    """Return a MetadataIndex, reusing a cached instance if still fresh."""
    key = str(index_dir.resolve())
    now = datetime.now(UTC).timestamp()
    if key in _metadata_cache:
        cache_time, cached = _metadata_cache[key]
        if now - cache_time < _METADATA_TTL_SECONDS:
            return cached
    md = MetadataIndex(index_dir=index_dir)
    md.load()
    _metadata_cache[key] = (now, md)
    return md


@dataclass
class DomainConfig:
    """Minimal domain config for dashboard computation."""

    id: str
    staleness_threshold_days: int = 90


def _compute_confidence_distribution(pages: list[dict]) -> DashboardConfidenceDistribution:
    """Compute confidence histogram buckets from page metadata list."""
    dist = DashboardConfidenceDistribution()
    for page in pages:
        score = page.get("confidence_score", page.get("confidence", 0.5))
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        if score < 0.3:
            dist.low += 1
        elif score < 0.6:
            dist.medium += 1
        else:
            dist.high += 1
    return dist


def _load_domains_config(wiki_base: Path) -> dict[str, DomainConfig]:
    """Load domain configurations from wiki_base/config/domains/."""
    domains: dict[str, DomainConfig] = {}

    # Also scan domains directory
    domains_dir = wiki_base / "domains"
    if domains_dir.exists():
        for domain_dir in domains_dir.iterdir():
            if (
                domain_dir.is_dir()
                and not domain_dir.is_symlink()
                and domain_dir.name not in domains
            ):
                domains[domain_dir.name] = DomainConfig(
                    id=domain_dir.name,
                    staleness_threshold_days=90,
                )

    return domains


def _get_recent_changes(
    wiki_base: Path,
    domain: str,
    domain_page_ids: set[str],
    limit: int = 10,
) -> list[DashboardRecentChange]:
    """Get recent changelog entries filtered to pages in the domain."""
    changelog = ChangeLog(changelog_dir=wiki_base / "changelog")
    changelog.load_index()

    # Collect recent changes, then filter to domain pages.
    # Fetch more when we have many domain pages to find matches within,
    # but cap at limit if domain is empty or small to avoid unnecessary I/O.
    if len(domain_page_ids) > 20:
        fetch_limit = limit * 5
    else:
        fetch_limit = limit * 3 if domain_page_ids else limit
    all_changes = changelog.get_recent_changes(limit=fetch_limit)
    domain_changes = [c for c in all_changes if c.page_id in domain_page_ids]

    # Sort newest first and take top `limit`
    domain_changes.sort(key=lambda c: c.timestamp, reverse=True)
    return [
        DashboardRecentChange(
            id=c.id,
            page_id=c.page_id,
            timestamp=c.timestamp,
            change_type=c.change_type,
            actor=c.actor,
        )
        for c in domain_changes[:limit]
    ]


def _get_last_governance_run(wiki_base: Path) -> DashboardLastGovernanceRun | None:
    """Read last governance run info from state/jobs.json."""
    jobs_path = wiki_base / "state" / "jobs.json"
    if not jobs_path.exists():
        return None

    try:
        import json  # noqa: PLC0415

        data = json.loads(jobs_path.read_text(encoding="utf-8"))
        last_run = data.get("govern", {})
        if not last_run:
            return None
        return DashboardLastGovernanceRun(
            last_run=last_run.get("last_run"),
            outcome=last_run.get("outcome", "unknown"),
            warnings=last_run.get("warning_count", 0),
        )
    except Exception:
        return None


def get_domain_dashboard(
    domain: str,
    wiki_root: Path,
) -> DashboardResponse:
    """Compute dashboard data for a single domain.

    Reads metadata index, changelog, and jobs.json — never writes new state.

    Args:
        domain: Domain identifier
        wiki_root: Base wiki directory

    Returns:
        DashboardResponse with page counts, confidence distribution, etc.

    Raises:
        DomainUnknownError: If the domain does not exist.
    """
    # Load domains to check validity
    domains_config = _load_domains_config(wiki_root)
    if domain not in domains_config:
        raise DomainUnknownError(f"Unknown domain: {domain}")

    staleness_days = domains_config[domain].staleness_threshold_days

    # Load metadata index (with TTL cache to avoid re-parsing on concurrent requests)
    index_dir = wiki_root / "index"
    metadata_index = _get_cached_metadata(index_dir)

    # Get pages in this domain
    domain_page_ids = set(metadata_index.by_domain.get(domain, set()))
    domain_pages = [
        metadata_index.pages[pid] for pid in domain_page_ids if pid in metadata_index.pages
    ]

    page_count = len(domain_pages)

    # Confidence distribution
    confidence_dist = _compute_confidence_distribution(domain_pages)

    # Low confidence count
    low_confidence_count = confidence_dist.low

    # Stale count — pages with updated_at older than threshold
    stale_cutoff = (datetime.now(UTC).timestamp() - (staleness_days * 86400)) * 1000
    stale_count = 0
    for page in domain_pages:
        updated_at = page.get("updated_at") or page.get("updated_at_ts") or page.get("_updated_at")
        if updated_at is None:
            continue
        try:
            if isinstance(updated_at, str):
                # Try ISO format first, fall back to millisecond timestamp
                try:
                    ts = datetime.fromisoformat(updated_at).timestamp() * 1000
                except ValueError:
                    ts = float(updated_at)
            else:
                ts = float(updated_at)
            if ts < stale_cutoff:
                stale_count += 1
        except (ValueError, TypeError):
            pass

    # Recent changes
    recent_changes = _get_recent_changes(wiki_root, domain, domain_page_ids, limit=10)

    # Last governance run
    last_governance_run = _get_last_governance_run(wiki_root)

    return DashboardResponse(
        domain=domain,
        page_count=page_count,
        confidence_distribution=confidence_dist,
        low_confidence_count=low_confidence_count,
        stale_count=stale_count,
        recent_changes=recent_changes,
        last_governance_run=last_governance_run,
    )
