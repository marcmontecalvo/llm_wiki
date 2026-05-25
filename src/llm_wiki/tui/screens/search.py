"""Search screen — text input + result display."""

from __future__ import annotations

import curses

from llm_wiki.tui.screens.base import Screen


class SearchScreen(Screen):
    name = "Search"

    def __init__(self, ctx) -> None:
        super().__init__("Search")
        self.query = ""
        self.prompt_mode = True
        self.results: list[dict] = []

    def render(self, stdscr, width, y, height):
        if self.prompt_mode:
            line = f" Query [{self.query}{'_' * max(0, 60 - len(self.query))}]"
            try:
                stdscr.addstr(y, 2, line[:width])
                ey = min(y + 1, height)
            except curses.error:
                ey = y

            if ey < height:
                try:
                    stdscr.addstr(
                        ey, 2, f" Results: {len(self.results)} found", curses.color_pair(2)
                    )
                except curses.error:
                    pass
        else:
            count = min(20, min(height - 1, len(self.results)))
            for i in range(count):
                r = self.results[i]
                title = str(r.get("title", r.get("page_id", "?")))[:50]
                domain = str(r.get("domain", "?"))[:15]
                conf = f"{r.get('confidence', 0):.2f}"
                line = f" {i + 1:>3}. {title} | {domain} | {conf}"
                try:
                    stdscr.addstr(y + i + 1, 2, line[:width])
                except curses.error:
                    pass
