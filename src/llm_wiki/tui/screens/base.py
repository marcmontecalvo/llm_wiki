"""Base screen class."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Screen:
    name: str

    def render(self, stdscr, width: int, y: int, height: int) -> None:
        """Render the screen. Subclasses override."""
        pass
