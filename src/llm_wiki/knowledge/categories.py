"""Canonical category registry for workspace facts.

Provides validation, normalization (including legacy household.* -> workspace.*
aliases), and listing of knowledge categories used by the Homefront integration.
"""

from __future__ import annotations

CANONICAL_CATEGORIES: frozenset[str] = frozenset(
    [
        "workspace.roster",
        "workspace.assignments",
        "workspace.pets",
        "workspace.appliances",
        "workspace.preferences",
        "workspace.schedule",
        "workspace.vehicles",
        "workspace.presence",
        "workspace.recurring_responsibilities",
        "workspace.rooms",
        "workspace.integrations",
        "workspace.voice_nodes",
    ]
)

CATEGORY_ALIASES: dict[str, str] = {
    "household.roster": "workspace.roster",
    "household.assignments": "workspace.assignments",
    "household.pets": "workspace.pets",
    "household.appliances": "workspace.appliances",
    "household.preferences": "workspace.preferences",
    "household.schedule": "workspace.schedule",
    "household.vehicles": "workspace.vehicles",
    "household.presence": "workspace.presence",
    "household.recurring_responsibilities": "workspace.recurring_responsibilities",
}


def normalize_category(raw: str) -> str:
    """Return the canonical category name; raise UnknownFactCategoryError if invalid."""
    from llm_wiki.exceptions import UnknownFactCategoryError

    canonical = CATEGORY_ALIASES.get(raw, raw)
    if canonical not in CANONICAL_CATEGORIES:
        raise UnknownFactCategoryError(canonical, sorted(CANONICAL_CATEGORIES))
    return canonical


def is_valid_category(category: str) -> bool:
    """Fast check if a category is in the canonical set."""
    return category in CANONICAL_CATEGORIES


def get_categories_list() -> dict:
    """Return the category registry with canonical names and aliases."""
    return {
        "canonical": sorted(CANONICAL_CATEGORIES),
        "aliases": dict(CATEGORY_ALIASES),
    }
