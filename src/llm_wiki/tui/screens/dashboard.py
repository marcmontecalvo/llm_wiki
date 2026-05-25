"""Dashboard screen — operations overview."""

from __future__ import annotations

from llm_wiki.tui.screens.base import Screen


class DashboardScreen(Screen):
    name = "Dashboard"

    def __init__(self, ctx) -> None:
        super().__init__("Dashboard")
        self.panel_data: dict[str, object] = {}

    def render(self, stdscr, width, y, height):
        panels = [
            "Daemon Health",
            "Wiki Health",
            "Ingestion Pipeline",
            "Governance Issues",
            "Query Activity",
        ]
        for i, panel in enumerate(panels):
            try:
                stdscr.addstr(y + i, 2, f" [P{i}] {panel}", 2)
            except Exception:
                pass
