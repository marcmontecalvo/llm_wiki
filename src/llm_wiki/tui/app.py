"""LLM Wiki TUI — Text-based terminal interface.

Entrypoint: `python -m llm_wiki.tui`
Usage requires `features.tui_enabled = true` in daemon.yaml.
"""

from __future__ import annotations

import curses
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

from llm_wiki.config.loader import load_config
from llm_wiki.tui.api import WikiAPI
from llm_wiki.tui.offline import OfflineReader
from llm_wiki.tui.screens.browse import BrowseScreen
from llm_wiki.tui.screens.dashboard import DashboardScreen
from llm_wiki.tui.screens.help import HelpScreen
from llm_wiki.tui.screens.issues import IssuesScreen
from llm_wiki.tui.screens.search import SearchScreen

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    daemon_url: str = ""
    username: str = ""
    password: str = ""
    wiki_base: str = ""
    api: object | None = None
    offline: OfflineReader | None = None
    connected: bool = True

    def __post_init__(self) -> None:
        if not self.daemon_url:
            self.daemon_url = os.environ.get("WIKI_DAEMON_URL", "http://127.0.0.1:3050")
        if not self.username:
            self.username = os.environ.get("WIKI_UI_USER", "admin")
        if not self.password:
            self.password = os.environ.get("WIKI_UI_PASSWORD", "")


def _load_config_and_creds() -> AppContext:
    """Load daemon.yaml features and credential overrides."""
    ctx = AppContext()

    # Check TUI gate
    try:
        cfg = load_config(os.environ.get("LLM_WIKI_BASE", "./wiki_system/config"))
        if not cfg.daemon.daemon.features.tui_enabled:
            print("TUI not enabled in config", file=sys.stderr)
            sys.exit(1)
    except Exception:
        # If config not found, TUI can still launch — it will show offline mode
        pass

    # Load credential overrides
    env_file = os.path.join(os.path.expanduser("~"), ".env")
    if os.path.isfile(env_file):
        for line in open(env_file):
            line = line.strip()
            if line.startswith("WIKI_UI_") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip()
                if k == "WIKI_UI_USER" and not ctx.username:
                    ctx.username = v
                elif k == "WIKI_UI_PASSWORD" and not ctx.password:
                    ctx.password = v

    creds_path = os.path.expanduser("~/.llm_wiki/credentials")
    if os.path.isfile(creds_path):
        for line in open(creds_path):
            line = line.strip()
            if line.startswith("username="):
                ctx.username = line.split("=", 1)[1].strip()
            elif line.startswith("password="):
                ctx.password = line.split("=", 1)[1].strip()

    return ctx


def _global_inputwrapper(stdscr, ctx: AppContext) -> None:
    """Main curses loop — input handler for all screens."""
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # selected
    curses.init_pair(2, curses.COLOR_GREEN, -1)  # success
    curses.init_pair(3, curses.COLOR_RED, -1)  # error
    curses.init_pair(4, curses.COLOR_YELLOW, -1)  # warning

    current: Any = SearchScreen(ctx)  # type: ignore[assignment]
    _screens = [
        ("S", current),
        ("B", BrowseScreen(ctx)),
        ("D", DashboardScreen(ctx)),
        ("I", IssuesScreen(ctx)),
        ("?", HelpScreen(ctx)),
    ]

    while True:
        # Refresh screen buffer
        pass
        stdscr.nodelay(False)
        stdscr.keypad(True)

        width, height = stdscr.getmaxyx()

        # Status bar
        status = "[connected]" if ctx.connected else "[DAEMON OFFLINE]"
        stdscr.attron(curses.color_pair(2))
        stdscr.addstr(0, 0, f" TUI {status}                    ")
        stdscr.attroff(curses.color_pair(2))

        # Body
        page_h = height - 3
        stdscr.move(1, 0)
        if current == HelpScreen(ctx):
            current.render(stdscr, width, 1, page_h)
        else:
            try:
                current.render(stdscr, width, 1, page_h)
            except RecursionError:
                stdscr.addstr(1, 0, "[render error]")

        # Key bindings hint
        key_h = max(1, min(height - 1, height))
        try:
            stdscr.addstr(
                key_h,
                0,
                " S:Search  B:Browse  D:Dashboard  I:Issues  ?:Help  Esc:Quit             ",
            )
        except curses.error:
            pass

        key = stdscr.getch()
        if key == 27:  # Esc
            break
        if key in (ord("s"), ord("S")):
            current = SearchScreen(ctx)
        elif key in (ord("b"), ord("B")):
            current = BrowseScreen(ctx)
        elif key in (ord("d"), ord("D")):
            current = DashboardScreen(ctx)
        elif key in (ord("i"), ord("I")):
            current = IssuesScreen(ctx)
        elif key in (ord("?"), ord("/")):
            current = HelpScreen(ctx)


def main() -> None:
    ctx = _load_config_and_creds()
    # Determine wiki_base from env if set
    import os

    if hasattr(ctx, "wiki_base") and not ctx.wiki_base:
        ctx.wiki_base = os.environ.get("WIKI_ROOT", "wiki_system")
    if ctx.wiki_base:
        ctx.offline = OfflineReader(ctx.wiki_base)
    # TUI is interactive — stdin is required
    if not sys.stdin.isatty():
        print(
            "TUI requires an interactive TTY. Run with `docker exec -it <container> python -m llm_wiki.tui`",
            file=sys.stderr,
        )
        sys.exit(1)
    # Try connecting to the daemon (always defaults to localhost in container)
    ctx.api = WikiAPI(ctx.daemon_url, ctx.username, ctx.password)
    try:
        status = ctx.api.get_daemon_status()
        ctx.connected = status.get("status") != "offline"
    except Exception:
        ctx.connected = False

    curses.wrapper(lambda scr: _global_inputwrapper(scr, ctx))


if __name__ == "__main__":
    main()
