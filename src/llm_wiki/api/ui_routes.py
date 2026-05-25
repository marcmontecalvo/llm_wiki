"""Web UI routes — /ui/* endpoints.

Served by FastAPI with Jinja2 templates. Protected by HTTP Basic Auth.
Feature-gated by `webui_enabled` in daemon.yaml features block.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import jinja2
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from llm_wiki.api.ui_auth import verify_ui_auth
from llm_wiki.query.search import WikiQuery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui", tags=["webui"])

# ── Rendered pages ──────────────────────────────────────────────────────


def ensure_auth(request: Request) -> None:
    """Raise HTTPException if auth is invalid.  Use as a Depends() call."""
    ui_password = getattr(request.app.state, "ui_password", "")
    if not ui_password:
        # Fallback: read from persisted password file (written at startup)
        _wiki_root = os.environ.get("WIKI_ROOT", "wiki_system")
        pw_file = Path(_wiki_root) / "state" / ".ui_password"
        try:
            ui_password = pw_file.read_text().strip()
        except Exception:
            pass
    if not ui_password:
        raise HTTPException(
            status_code=500, detail="UI not configured — no password source available"
        )
    if not verify_ui_auth(request, ui_password):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )


PAGE_TEMPLATES = {
    "home": "home",
    "search": "search",
    "browse": "browse",
    "dashboard": "dashboard",
    "issues": "issues",
    "page_detail": "page_detail",
}

SNIPPET_TEMPLATES = {
    "snippets/domain_nav",
    "snippets/search_results",
    "snippets/browse_results",
    "snippets/page_preview",
}

# ── Jinja2 cache ────────────────────────────────────────────────────────

_jinja_env: jinja2.Environment | None = None
_jinja_dir: str | None = None


def _get_jinja_env() -> jinja2.Environment:
    global _jinja_env, _jinja_dir
    if _jinja_env is None:
        # Templates live at llm_wiki/templates/ (sibling of api/)
        _tmp_dir = str(Path(__file__).resolve().parent.parent / "templates")
        _jinja_dir = _tmp_dir
        _jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(_tmp_dir),
            autoescape=True,
        )
    return _jinja_env


@router.get("/", response_class=HTMLResponse)
async def ui_home(request: Request):
    ensure_auth(request)
    # Redirect to search as the default landing page
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/ui/search", status_code=303)


@router.get("/search", response_class=HTMLResponse)
async def ui_search(request: Request):
    ensure_auth(request)
    _ui_password = getattr(request.app.state, "ui_password", "")
    _ui_user = getattr(request.app.state, "ui_user", "admin")
    return _render_page(
        "search",
        {
            "title": "Search",
            "ui_user": _ui_user,
            "ui_password": _ui_password,
        },
    )


@router.get("/browse", response_class=HTMLResponse)
async def ui_browse(request: Request):
    ensure_auth(request)
    wiki: WikiQuery = request.app.state.wiki
    domains_cfg = getattr(wiki, "_wiki_config", None)
    cfg_list = None
    if domains_cfg is not None:
        raw = getattr(domains_cfg, "domains", None)
        if isinstance(raw, list):
            cfg_list = raw
        else:
            cfg_list = getattr(raw, "domains", None) if raw is not None else None
    domain_list = []
    if cfg_list is not None:
        for d in cfg_list:
            domain_list.append({"id": d.id, "title": getattr(d, "title", d.id)})
    elif getattr(wiki.wiki_base, "exists", None):
        domains_dir = wiki.wiki_base / "domains"
        if domains_dir.exists():
            for dd in domains_dir.iterdir():
                if dd.is_dir() and not dd.is_symlink():
                    domain_list.append({"id": dd.name, "title": dd.name})
    _ui_password = getattr(request.app.state, "ui_password", "")
    _ui_user = getattr(request.app.state, "ui_user", "admin")
    return _render_page(
        "browse",
        {
            "title": "Browse",
            "domains": domain_list,
            "wiki": wiki,
            "ui_user": _ui_user,
            "ui_password": _ui_password,
        },
    )


@router.get("/dashboard", response_class=HTMLResponse)
async def ui_dashboard(request: Request):
    ensure_auth(request)
    return _render_page("dashboard", {"title": "Dashboard"})


@router.get("/issues", response_class=HTMLResponse)
async def ui_issues(request: Request):
    ensure_auth(request)
    return _render_page("issues", {"title": "Issues"})


@router.get("/page/{page_id}", response_class=HTMLResponse)
async def ui_page_detail(request: Request, page_id: str):
    ensure_auth(request)
    return _render_page("page_detail", {"title": f"Page: {page_id}", "page_id": page_id})


def _render_page(template: str, context: dict, status_code: int = 200) -> HTMLResponse:
    """Render a full page (optionally extends base.html) via Jinja2."""
    name = f"{template}.html"
    env = _get_jinja_env()
    try:
        return HTMLResponse(
            content=env.get_template(name).render(**context),
            status_code=status_code,
        )
    except jinja2.TemplateNotFound:
        return HTMLResponse(
            content=f"<html><body><h1>Coming soon — '{template}'</h1></body></html>",
            status_code=501,
        )


# ── HTMX snippet API routes ─────────────────────────────────────────────


@router.get("/api/domains-tree")
async def ui_domains_tree(request: Request):
    """Return configured domains for the sidebar nav."""
    ensure_auth(request)
    wiki: WikiQuery = request.app.state.wiki
    domains_cfg = getattr(wiki, "_wiki_config", None)
    cfg_list = None
    if domains_cfg is not None:
        raw = getattr(domains_cfg, "domains", None)
        if isinstance(raw, list):
            cfg_list = raw
        else:
            cfg_list = getattr(raw, "domains", None) if raw is not None else None
    domain_list = []
    if cfg_list is not None:
        for d in cfg_list:
            page_count = len(wiki.metadata_index.by_domain.get(d.id, set()))
            domain_list.append(
                {
                    "name": d.id,
                    "title": getattr(d, "title", d.id),
                    "scope": getattr(d, "scope", "shared"),
                    "page_count": page_count,
                }
            )
    elif getattr(wiki.wiki_base, "exists", None):
        domains_dir = wiki.wiki_base / "domains"
        if domains_dir.exists():
            for dd in domains_dir.iterdir():
                if dd.is_dir() and not dd.is_symlink():
                    page_count = len(wiki.metadata_index.by_domain.get(dd.name, set()))
                    domain_list.append(
                        {
                            "name": dd.name,
                            "title": dd.name,
                            "scope": "shared",
                            "page_count": page_count,
                        }
                    )
    _ui_password = getattr(request.app.state, "ui_password", "")
    _ui_user = getattr(request.app.state, "ui_user", "admin")
    return _render_page(
        "snippets/domain_nav",
        {
            "title": "Domains",
            "current_domain": "",
            "domains": domain_list,
            "ui_user": _ui_user,
            "ui_password": _ui_password,
        },
    )


@router.get("/api/search")
async def ui_search_htmx(request: Request):
    """HTMX proxy for search — returns result table rows."""
    ensure_auth(request)
    q = request.query_params.get("q", "")
    if not q:
        return _render_page("snippets/search_results", {"results": []}, status_code=501)
    wiki: WikiQuery = request.app.state.wiki
    pages = await asyncio.to_thread(wiki.search, q, limit=50)
    return _render_page("snippets/search_results", {"results": pages})


@router.get("/api/search-json")
async def ui_search_json(request: Request):
    """JSON search endpoint for JS fetch calls. Returns full page metadata."""
    ensure_auth(request)
    q = request.query_params.get("q", "")
    if not q:
        return {"results": []}
    wiki: WikiQuery = request.app.state.wiki
    results = await asyncio.to_thread(wiki.search, q, limit=50)
    enriched = []
    for r in results:
        page_id = r.get("page_id")
        enriched.append(
            {
                "page_id": page_id,
                "title": r.get("title", page_id),
                "domain": r.get("domain", "general"),
                "kind": r.get("kind", "page"),
                "confidence": r.get("confidence", 0.0),
                "score": r.get("score", 0.0),
            }
        )
    return {"results": enriched}


@router.get("/api/pages")
async def ui_pages_htmx(
    request: Request,
    domain: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    confidence_min: float | None = Query(default=None),
    tags: str | None = Query(default=None),
):
    """HTMX proxy for pages listing — returns filtered page table rows."""
    ensure_auth(request)
    wiki: WikiQuery = request.app.state.wiki
    page_items, _ = await asyncio.to_thread(
        wiki.list_pages,
        domain=domain,
        kind=kind,
        limit=200,
    )
    # Apply additional filters not supported by list_pages
    results = []
    for item in page_items:
        if confidence_min is not None:
            conf = item.get("confidence", 0.0)
            # Normalize boolean confidence to float
            if isinstance(conf, bool):
                conf = 1.0 if conf else 0.0
            conf = float(conf)
            if conf < confidence_min:
                continue
        if tags is not None and tags:
            page_tags = {str(t).lower() for t in item.get("tags", [])}
            required = {t.strip().lower() for t in tags.split(",")}
            if not required.issubset(page_tags):
                continue
        results.append(item)
    return _render_page("snippets/browse_results", {"pages": results})


@router.get("/api/page/{page_id}")
async def ui_page_detail_htmx(request: Request, page_id: str):
    """HTMX proxy for page detail — returns front matter + connections."""
    ensure_auth(request)
    return _render_page(
        "snippets/page_preview",
        {
            "page_id": page_id,
            "main": [],
            "connects_to": [],
            "connected_from": [],
        },
    )


@router.get("/api/dashboard")
async def ui_dashboard_htmx(request: Request):
    ensure_auth(request)
    return _render_page("dashboard", {"title": "Dashboard"})
