"""Page view screen — full page detail display."""

from __future__ import annotations

from llm_wiki.tui.screens.base import Screen


class PageViewScreen(Screen):
    name = "Page View"

    def __init__(self, ctx, page_id: str = "") -> None:
        super().__init__("Page View")
        self.page_id = page_id
        self.page_data: dict = {}
        self.connects_to: list[dict] = []
        self.connected_from: list[dict] = []

    def render(self, stdscr, width, y, height):
        if not self.page_id:
            return
        try:
            stdscr.addstr(y, 2, f" Page: {self.page_id}", 2)
            title = str(self.page_data.get("title", ""))[:50]
            stdscr.addstr(y + 1, 4, f" Title: {title}")
            stdscr.addstr(y + 2, 4, f" Domain: {self.page_data.get('domain', '?')}")
            stdscr.addstr(y + 3, 4, f" Kind: {self.page_data.get('kind', '?')}")
        except Exception:
            pass
