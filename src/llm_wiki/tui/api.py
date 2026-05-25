"""REST API client for the LLM Wiki daemon.

Uses HTTP Basic Auth via requests.Session().
"""

from __future__ import annotations

import logging
import time
from typing import Any, cast

logger = logging.getLogger(__name__)


class WikiAPI:
    """HTTP client for the wiki daemon REST API.

    All calls use Basic Auth via a requests.Session.  Transient errors
    are retried with exponential backoff (up to 3 attempts).
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = type("AuthSession", (), {})()
        # Manually set up a requests.Session for Basic Auth
        import requests  # type: ignore[import-untyped]

        rs = requests.Session()
        rs.auth = (username, password)
        self.session = rs

    def _req(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        last_err: Exception | None = None  # type: ignore[assignment]
        for attempt in range(3):
            try:
                resp = self.session.request(method, url, **kwargs)
                if resp.status_code >= 500:
                    raise RuntimeError(f"HTTP {resp.status_code}")
                return cast(Any, resp.json())
            except Exception as exc:
                last_err = exc
                logger.debug("Retry %d failed for %s %s: %s", attempt + 1, method, url, exc)
                time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"Failed after 3 attempts: {last_err}")

    def list_pages(
        self,
        domain: str | None = None,
        kind: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
        archived: bool = False,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "include_archived": archived}
        if domain:
            params["domain"] = domain
        if kind:
            params["kind"] = kind
        if cursor:
            params["cursor"] = cursor
        return cast(dict, self._req("GET", "/v1/pages", params=params))

    def read_page(self, page_id: str) -> dict:
        return cast(dict, self._req("GET", f"/v1/pages/{page_id}"))

    def search(
        self, q: str, domain: str | None = None, limit: int = 50, archived: bool = False
    ) -> dict:
        body: dict[str, Any] = {"query": q, "limit": limit, "archived": archived}
        if domain:
            body["domain"] = domain
        return cast(dict, self._req("POST", "/v1/query", json=body))

    def search_get(self, q: str, domain: str | None = None) -> dict:
        params: dict[str, Any] = {"q": q}
        if domain:
            params["domain"] = domain
        return cast(dict, self._req("GET", "/ui/api/search", params=params))

    def list_domains(self) -> list[dict]:
        return cast(list[dict], self._req("GET", "/v1/domains"))

    def get_dashboard(self, domain: str) -> dict:
        return cast(dict, self._req("GET", f"/v1/domains/{domain}/dashboard"))

    def get_daemon_status(self) -> dict:
        try:
            return cast(dict, self._req("GET", "/v1/health"))
        except Exception:
            return {"status": "offline"}

    def get_backlinks(self, page_id: str) -> list[dict]:
        """Resolve backlinks by scanning wiki pages (denormalized)."""
        import asyncio  # noqa: PLC0415

        from llm_wiki.deps import get_wiki  # noqa: PLC0415

        wiki = asyncio.run(get_wiki(None))  # type: ignore[arg-type]
        index = getattr(wiki.metadata_index, "reverse_links", {})  # type: ignore[attr-defined]
        return cast(list[dict], index.get(page_id, []))
