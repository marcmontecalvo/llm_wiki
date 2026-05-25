"""Help screen — key bindings reference."""

from __future__ import annotations

from llm_wiki.tui.screens.base import Screen


class HelpScreen(Screen):
    name = "Help"

    def __init__(self, ctx) -> None:
        super().__init__("Help")

    def render(self, stdscr, width, y, height):
        lines = [
            " Key Bindings:",
            "   S — Search",
            "   B — Browse",
            "   D — Dashboard",
            "   I — Issues",
            "   P — Page view",
            "   R — Refresh",
            "   F — Filter modal",
            "   ? — This help",
            "   Esc — Quit",
        ]
        for i, line in enumerate(lines):
            try:
                stdscr.addstr(y + i, 2, line[:width])
            except Exception:
                pass
