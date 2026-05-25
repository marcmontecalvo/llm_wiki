"""Offline mode screen."""

from __future__ import annotations

from llm_wiki.tui.screens.base import Screen


class OfflineScreen(Screen):
    name = "Offline"

    def __init__(self, ctx) -> None:
        super().__init__("Offline")
        self.wiki_base = ctx.wikipedia_base if hasattr(ctx, "wiki_base") else ""

    def render(self, stdscr, width, y, height):
        try:
            stdscr.addstr(y, 2, " DAEMON OFFLINE", 3)
            stdscr.addstr(y + 1, 2, "(Use file-system fallback — no search/backlinks)")
        except Exception:
            pass
