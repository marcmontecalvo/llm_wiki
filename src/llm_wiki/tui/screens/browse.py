"""Browse screen — file system / API page listing."""

from __future__ import annotations

from llm_wiki.tui.screens.base import Screen


class BrowseScreen(Screen):
    name = "Browse"

    def __init__(self, ctx) -> None:
        super().__init__("Browse")
        self.filter_domain = ""
        self.filter_kind = ""
        self.pages: list[dict] = []

    def render(self, stdscr, width, y, height):
        line = " Browse — filter by domain/kind/filter/confidence"
        try:
            stdscr.addstr(y, 2, line[:width])
        except Exception:
            pass
        line2 = f" Domains: {len(self.pages)} pages found"
        try:
            stdscr.addstr(y + 1, 2, line2[:width])
        except Exception:
            pass
