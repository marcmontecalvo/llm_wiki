"""Shared path resolution for wiki system."""

import os
from pathlib import Path

_WIKI_ROOT = os.environ.get("WIKI_ROOT", "wiki_system")
WIKI_ROOT = Path(_WIKI_ROOT)


def get_wiki_root() -> Path:
    """Return the configured wiki root directory."""
    return WIKI_ROOT


def resolve_wiki_base(wiki_base: Path | None) -> Path:
    """Resolve a wiki_base argument, falling back to WIKI_ROOT env var."""
    if wiki_base is not None:
        return wiki_base
    return WIKI_ROOT
