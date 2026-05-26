"""Web UI routes — /ui/* endpoints.

Served by FastAPI with Jinja2 templates. Protected by HTTP Basic Auth.
Feature-gated by `webui_enabled` in daemon.yaml features block.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import jinja2
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from llm_wiki.api.ui_auth import verify_ui_auth
from llm_wiki.daemon.execution_store import JobExecutionStore
from llm_wiki.query.log import QueryLogStore
from llm_wiki.query.search import WikiQuery
from llm_wiki.utils.frontmatter import parse_frontmatter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui", tags=["webui"])

# ── Rendered pages ──────────────────────────────────────────────────────


def ensure_auth(request: Request) -> None:
    """Raise HTTPException if auth is invalid."""
    ui_password = getattr(request.app.state, "ui_password", "")
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
    "editor": "editor",
    "domain_overview": "domain_overview",
}

SNIPPET_TEMPLATES = {
    "snippets/domain_nav",
    "snippets/search_results",
    "snippets/browse_results",
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
    return _render_page(
        "dashboard",
        {
            "title": "Dashboard",
            "ui_user": getattr(request.app.state, "ui_user", "admin"),
            "ui_password": getattr(request.app.state, "ui_password", ""),
        },
    )


@router.get("/issues", response_class=HTMLResponse)
async def ui_issues(request: Request):
    ensure_auth(request)
    return _render_page(
        "issues",
        {
            "title": "Issues",
            "ui_user": getattr(request.app.state, "ui_user", "admin"),
            "ui_password": getattr(request.app.state, "ui_password", ""),
        },
    )


@router.get("/editor", response_class=HTMLResponse)
async def ui_editor(request: Request):
    """Editor landing — empty form.  Optionally ?page_id=X to edit existing."""
    ensure_auth(request)
    page_id = request.query_params.get("page_id", "")
    _ui_password = getattr(request.app.state, "ui_password", "")
    _ui_user = getattr(request.app.state, "ui_user", "admin")
    return _render_page(
        "editor",
        {
            "title": "Editor",
            "ui_user": _ui_user,
            "ui_password": _ui_password,
            "page_id": page_id,
        },
    )


@router.get("/domain/{domain_id}", response_class=HTMLResponse)
async def ui_domain_overview(request: Request, domain_id: str):
    ensure_auth(request)
    _ui_password = getattr(request.app.state, "ui_password", "")
    _ui_user = getattr(request.app.state, "ui_user", "admin")
    return _render_page(
        "domain_overview",
        {
            "title": "Domain: " + domain_id,
            "ui_user": _ui_user,
            "ui_password": _ui_password,
            "domain_id": domain_id,
        },
    )


@router.get("/page/{page_id}", response_class=HTMLResponse)
async def ui_page_detail(request: Request, page_id: str):
    ensure_auth(request)
    return _render_page(
        "page_detail",
        {
            "title": f"Page: {page_id}",
            "page_id": page_id,
            "ui_user": getattr(request.app.state, "ui_user", "admin"),
            "ui_password": getattr(request.app.state, "ui_password", ""),
        },
    )


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


# ── Dashboard aggregation endpoint ──────────────────────────────────────


@router.get("/api/dashboard-data", response_model=None)
async def ui_dashboard_data(request: Request):
    """Aggregate all data sources for the operations dashboard."""
    ensure_auth(request)
    wiki: WikiQuery = request.app.state.wiki
    wiki_base: Path = wiki.wiki_base

    # 1. Daemon health
    health = await asyncio.to_thread(_get_health, wiki)

    # 2. Scheduler status
    scheduler_info = await asyncio.to_thread(_get_scheduler_info, wiki)

    # 3. Domain list + per-domain dashboards
    domains, domain_dashboards = await asyncio.to_thread(_get_domains, wiki, wiki_base)

    # Aggregate totals
    total_pages = sum(d.get("page_count", 0) for d in domains)
    total_low_conf = sum(d.get("low_confidence_count", 0) for d in domain_dashboards)
    total_stale = sum(d.get("stale_count", 0) for d in domain_dashboards)

    # 4. Daemon job statuses
    job_statuses = await asyncio.to_thread(_get_daemon_jobs, wiki_base)

    # 5. Inbox queues
    inbox_counts = await asyncio.to_thread(_get_inbox_counts, wiki_base)

    # 6. Governance
    governance = await asyncio.to_thread(_get_governance, wiki_base)

    # 7. Query activity
    query_stats = await asyncio.to_thread(_get_query_activity, wiki_base)

    return {
        "health": health,
        "scheduler": scheduler_info,
        "domains": domains,
        "domain_dashboards": domain_dashboards,
        "total_pages": total_pages,
        "total_low_confidence": total_low_conf,
        "total_stale": total_stale,
        "jobs": job_statuses,
        "inbox": inbox_counts,
        "governance": governance,
        "query_stats": query_stats,
    }


def _get_health(wiki: WikiQuery) -> dict:
    """Return daemon health based on PID file and index existence."""
    wiki_base = wiki.wiki_base
    index_path = wiki.index_dir / "index.faiss"
    index_loaded = index_path.exists()

    # PID check for daemon
    pid_file = wiki_base / "state" / "daemon.pid"
    daemon_running = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            daemon_running = True
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    return {"daemon_running": daemon_running, "index_loaded": index_loaded}


_SchedulerNotFound = ModuleNotFoundError


def _get_scheduler_info(wiki: WikiQuery) -> dict:
    """Get scheduler state from the wiki instance."""
    sched = getattr(wiki, "_scheduler", None)
    if sched is None:
        return {"running": False, "job_count": 0, "uptime_seconds": None, "recent_errors": 0}

    try:
        from apscheduler.schedulers.background import (
            BackgroundScheduler,  # type: ignore[import-untyped]  # noqa: PLC0415
        )

        if isinstance(sched.scheduler, BackgroundScheduler):
            running = sched.scheduler.running
            uptime = None
            started = getattr(sched, "_started_at", None)
            if running and started:
                uptime = round(
                    (
                        __import__("datetime", fromlist=["datetime"]).datetime.now(
                            __import__("datetime", fromlist=["datetime"]).timezone.utc
                        )
                        - started
                    ).total_seconds(),
                    2,
                )

        return {
            "running": running,
            "job_count": len(sched.get_jobs()),
            "uptime_seconds": uptime,
            "recent_errors": sched.health().get("recent_errors", 0),
        }
    except _SchedulerNotFound:
        return {"running": False, "job_count": 0, "uptime_seconds": None, "recent_errors": 0}


def _get_domains(wiki: WikiQuery, wiki_base: Path) -> tuple[list[dict], list[dict]]:
    """Return domains list + per-domain dashboard data."""
    from llm_wiki.api.models import DashboardResponse  # noqa: PLC0415
    from llm_wiki.api.services.dashboard import get_domain_dashboard  # noqa: PLC0415
    from llm_wiki.config.loader import load_config  # noqa: PLC0415
    from llm_wiki.exceptions import DomainUnknownError  # noqa: PLC0415

    domains = []
    domain_dashboards = []

    try:
        config = load_config(wiki_base / "config")
        for dc in config.domains.domains if config.domains else []:
            domain_id = dc.id
            scope = getattr(dc, "title", "shared")
            page_count = len(wiki.metadata_index.by_domain.get(domain_id, set()))
            domains.append(
                {
                    "name": domain_id,
                    "title": scope,
                    "scope": getattr(dc, "scope", "shared"),
                    "page_count": page_count,
                }
            )
            try:
                dash = get_domain_dashboard(domain_id, wiki_base)
                dd = dash.model_dump() if isinstance(dash, DashboardResponse) else dash
                domain_dashboards.append({"domain": domain_id, **dd})
            except (DomainUnknownError, Exception):
                domain_dashboards.append({"domain": domain_id})
    except Exception:
        # Fallback: discover from filesystem
        domains_dir = wiki_base / "domains"
        if domains_dir.exists():
            for dd_dir in sorted(domains_dir.iterdir()):
                if dd_dir.is_dir() and not dd_dir.is_symlink():
                    count = len(list((dd_dir / "pages").glob("*.md")))
                    domains.append(
                        {
                            "name": dd_dir.name,
                            "title": dd_dir.name,
                            "scope": "shared",
                            "page_count": count,
                        }
                    )

    return domains, domain_dashboards


def _get_daemon_jobs(wiki_base: Path) -> list[dict]:
    """Get daemon job statuses from execution store."""
    try:
        store = JobExecutionStore(state_dir=wiki_base / "state")
        job_names = store.job_names()
        result = []
        for name in job_names:
            history = store.get_history(name)
            last = history.get_last()
            job_info: dict[str, Any] = {
                "name": name,
                "status": last.status.value if last else "unknown",
                "last_run": last.started_at.isoformat() if last and last.started_at else None,
            }
            job_info["recent_history"] = [e.to_dict() for e in list(history.executions)[-3:]]
            result.append(job_info)
        return result
    except Exception:
        return []


def _get_inbox_counts(wiki_base: Path) -> dict:
    """Count files in inbox staging areas."""
    counts = {}
    for folder in ["new", "staging", "processing", "failed", "done"]:
        folder_path = wiki_base / "inbox" / folder
        if folder_path.exists():
            counts[folder] = len(list(folder_path.glob("*")))
    return counts


def _get_governance(wiki_base: Path) -> dict:
    """Load latest governance check result."""
    gov_dir = wiki_base / "state" / "job_executions"
    gov_file = gov_dir / "governance_check.json"

    if not gov_file.exists():
        return {"status": "never_run"}

    try:
        data = json.loads(gov_file.read_text())
        executions = data.get("executions", [])
        if executions:
            latest = executions[0]
            return {
                "status": "ok",
                "last_run": latest.get("started_at"),
                "result": latest.get("result", {}),
            }
        return {"status": "unknown"}
    except Exception:
        return {"status": "error"}


def _get_query_activity(wiki_base: Path) -> dict:
    """Query log stats."""
    try:
        log_path = wiki_base / "state" / "query_log.db"
        if log_path.exists():
            store = QueryLogStore(log_path)
            s = store.stats()
            return {
                "total_queries": s.get("total_rows", 0),
                "oldest": s.get("oldest_entry"),
                "top_queries": s.get("top_queries", []),
            }
    except Exception:
        pass
    return {"total_queries": 0}


# ── HTMX snippet API routes ─────────────────────────────────────────────


@router.get("/api/domains-tree", response_model=None)
async def ui_domains_tree(request: Request):
    """Return configured domains as JSON for the sidebar nav."""
    ensure_auth(request)
    wiki: WikiQuery = request.app.state.wiki
    wiki_base = wiki.wiki_base
    domain_list = []
    try:
        from llm_wiki.config.loader import load_config  # noqa: PLC0415

        config = load_config(wiki_base / "config")
        for dc in config.domains.domains if config.domains else []:
            page_count = len(wiki.metadata_index.by_domain.get(dc.id, set()))
            domain_list.append(
                {
                    "name": dc.id,
                    "title": getattr(dc, "title", dc.id),
                    "scope": getattr(dc, "scope", "shared"),
                    "page_count": page_count,
                }
            )
    except Exception:
        domains_dir = wiki_base / "domains"
        if domains_dir.exists():
            for dd in domains_dir.iterdir():
                if dd.is_dir() and not dd.is_symlink():
                    count = len(list((dd / "pages").glob("*.md")))
                    domain_list.append(
                        {
                            "name": dd.name,
                            "title": dd.name,
                            "scope": "shared",
                            "page_count": count,
                        }
                    )
    return {"domains": domain_list}


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
async def ui_page_detail_api(request: Request, page_id: str):
    """Return page data as JSON for UI consumption."""
    ensure_auth(request)
    wiki: WikiQuery = request.app.state.wiki
    wiki_base = wiki.wiki_base

    # Read content from filesystem
    found = False
    page_content = ""
    fm: dict = {}
    for dd in (wiki_base / "domains").iterdir():
        if not dd.is_dir():
            continue
        pf = dd / "pages" / f"{page_id}.md"
        if pf.exists():
            content = await asyncio.to_thread(pf.read_text, encoding="utf-8")
            fm, body = parse_frontmatter(content)
            page_content = body
            found = True
            break
    if not found:
        sf = wiki_base / "shared" / f"{page_id}.md"
        if sf.exists():
            content = await asyncio.to_thread(sf.read_text, encoding="utf-8")
            fm, body = parse_frontmatter(content)
            page_content = body

    if not found:
        raise HTTPException(status_code=404, detail=f"Page not found: {page_id}")

    # Backlinks
    reverse_links: dict = getattr(wiki.metadata_index, "reverse_links", {})
    bl = reverse_links.get(page_id, [])
    forward_links = bl.get("forward_links", []) if isinstance(bl, dict) else []
    backlinks = bl.get("backlinks", []) if isinstance(bl, dict) else []

    return {
        "page_id": page_id,
        "title": fm.get("title", page_id),
        "content": page_content,
        "frontmatter": fm,
        "domain": fm.get("domain", "general"),
        "kind": fm.get("kind", "page"),
        "confidence": fm.get("confidence", 0.0),
        "authority_score": fm.get("authority_score", 0.0),
        "connects_to": forward_links,
        "connected_from": backlinks,
    }
