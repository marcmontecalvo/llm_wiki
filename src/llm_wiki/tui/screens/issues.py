"""Issues screen — governance findings display."""

from __future__ import annotations

from llm_wiki.tui.screens.base import Screen


class IssuesScreen(Screen):
    name = "Issues"

    def __init__(self, ctx) -> None:
        super().__init__("Issues")
        self.issues: list[dict] = []

    def render(self, stdscr, width, y, height):
        line = f" Issues: {len(self.issues)} findings"
        try:
            stdscr.addstr(y, 2, line[:width])
        except Exception:
            pass
