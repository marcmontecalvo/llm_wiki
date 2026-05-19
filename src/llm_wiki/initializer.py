"""Wiki directory structure initializer and shared bootstrap.

Provides idempotent setup of the wiki directory structure so that the
service can start on a fresh (empty) volume without FileNotFoundError.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from llm_wiki.api.user_jobs import UserJobStore
from llm_wiki.config.loader import WikiConfig
from llm_wiki.query.search import WikiQuery

_DOMAIN_SUBDIRS = ("pages", "queue", "concepts", "entities", "synthesis")
_COMMON_SUBDIRS = (
    "shared/concepts",
    "shared/entities",
    "shared/synthesis",
    "inbox/new",
    "inbox/processing",
    "inbox/failed",
    "inbox/done",
    "exports",
    "logs",
    "state",
)

logger = logging.getLogger(__name__)


class WikiInitializer:
    """Creates and manages the wiki directory structure."""

    REQUIRED_SUBDIRS = (_DOMAIN_SUBDIRS, _COMMON_SUBDIRS)

    @classmethod
    def initialize(cls, wiki_root: Path | str) -> None:
        """Create all required subdirectories under *wiki_root*.

        Idempotent — safe to call multiple times.

        Args:
            wiki_root: Path to the wiki root directory.
        """
        root = Path(wiki_root)
        root.mkdir(parents=True, exist_ok=True)
        # Domain root — domains themselves are created per-domain below
        (root / "domains").mkdir(parents=True, exist_ok=True)
        # Generic dirs shared by all domains
        for subdir in _COMMON_SUBDIRS:
            (root / subdir).mkdir(parents=True, exist_ok=True)

    @classmethod
    def initialize_domain(cls, wiki_root: Path | str, domain: str) -> None:
        """Create subdirectories for a specific domain.

        Args:
            wiki_root: Path to the wiki root directory.
            domain: Domain name.
        """
        root = Path(wiki_root)
        for subdir in _DOMAIN_SUBDIRS:
            (root / "domains" / domain / subdir).mkdir(parents=True, exist_ok=True)

    @classmethod
    def initialize_all_domains(cls, wiki_root: Path | str, domains: list[str]) -> None:
        """Create subdirectories for all configured domains.

        Args:
            wiki_root: Path to the wiki root directory.
            domains: List of domain names.
        """
        root = Path(wiki_root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "domains").mkdir(parents=True, exist_ok=True)
        for domain in domains:
            cls.initialize_domain(root, domain)


def _maybe_init_wiki_root(wiki_root: Path | str) -> None:
    """Initialize the wiki root only if it appears to be uninitialised.

    Checks for the presence of ``domains/`` — if it exists the structure is
    assumed to already be initialised and nothing is done.  Otherwise
    :class:`WikiInitializer` is used to create the full directory tree.

    Args:
        wiki_root: Path to the wiki root directory.
    """
    root = Path(wiki_root)
    if (root / "domains").exists():
        return
    WikiInitializer.initialize(root)


def boot_wiki(
    wiki_root: Path | None = None,
    config_dir: Path | None = None,
) -> tuple[WikiQuery, WikiConfig | None, UserJobStore, dict]:
    """Bootstrap wiki, config, and related app state.

    This is the shared bootstrap path used by both FastAPI lifespan and
    stdio transport (``python -m llm_wiki.mcp.server``).  It honours
    ``WIKI_ROOT`` and ``WIKI_CONFIG_DIR`` environment variables.

    Ideal producer — same order as :func:`llm_wiki.app.lifespan`.

    Args:
        wiki_root: Explicit wiki root path (defaults to ``WIKI_ROOT`` env
            var, then ``"wiki_system"``).
        config_dir: Explicit config directory path (defaults to
            ``WIKI_CONFIG_DIR`` env var, then ``"config"``).

    Returns:
        Tuple of ``(wiki, wiki_config, user_job_store, deep_jobs)``.
    """
    from llm_wiki.api.user_jobs import get_user_job_store
    from llm_wiki.config.loader import load_config
    from llm_wiki.query.search import WikiQuery

    # Resolve wiki root
    _wiki_root = (
        wiki_root if wiki_root is not None else Path(os.environ.get("WIKI_ROOT", "wiki_system"))
    )
    wiki_root = Path(_wiki_root)

    # Resolve config dir
    _config_dir = (
        config_dir if config_dir is not None else Path(os.environ.get("WIKI_CONFIG_DIR", "config"))
    )
    config_dir = Path(_config_dir)

    # Initialize directories first
    _maybe_init_wiki_root(wiki_root)

    # Load config (non-fatal — MCP may have no config dir)
    wiki_config = None
    try:
        wiki_config = load_config(config_dir)
    except Exception:
        logger.warning("Config load failed (non-fatal for MCP bootstrap)")

    # Build indexes
    wiki = WikiQuery(wiki_base=wiki_root, index_dir=wiki_root / "index")

    # UserJobStore — shared factory
    user_job_store = get_user_job_store(wiki_root)

    # Deep query tracking
    deep_jobs: dict = {}

    return wiki, wiki_config, user_job_store, deep_jobs
