"""Wiki directory structure initializer.

Provides idempotent setup of the wiki directory structure so that the
service can start on a fresh (empty) volume without FileNotFoundError.
"""

from pathlib import Path

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
