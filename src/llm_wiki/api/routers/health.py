"""Health and daemon status endpoints.

Routes:
    - GET /v1/health
    - GET /v1/daemon/status
    - GET /v1/daemon/jobs
"""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, Request

from llm_wiki.api.models import (
    DaemonStatusResponse,
    HealthResponse,
    IngestStatusResponse,
    JobStatus,
)
from llm_wiki.config.loader import load_config
from llm_wiki.daemon.execution_store import JobExecutionStore
from llm_wiki.daemon.models import JobStatus as JobStatusEnum
from llm_wiki.deps import get_wiki
from llm_wiki.query.search import WikiQuery

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    request: Request, wiki: WikiQuery = Depends(get_wiki),
) -> HealthResponse:
    """Return service health summary."""
    wiki_base = wiki.wiki_base

    # Index loaded — check if index .faiss file exists (disk I/O)
    index_path = wiki.index_dir / "index.faiss"
    index_loaded: bool = await asyncio.to_thread(index_path.exists)

    # Scheduler state
    scheduler_state = "unknown"
    sched = getattr(wiki, "_scheduler", None)
    if sched is not None:
        backend = getattr(sched, "scheduler", None)
        if backend is not None and getattr(backend, "running", False):
            scheduler_state = "running"
        else:
            scheduler_state = "stopped"

    # Daemon liveness — check PID file (disk I/O)
    daemon_running = False
    pid_file = wiki_base / "state" / "daemon.pid"
    if await asyncio.to_thread(pid_file.exists):
        try:
            pid_text = await asyncio.to_thread(pid_file.read_text)
            pid = int(pid_text.strip())
            os.kill(pid, 0)
            daemon_running = True
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            daemon_running = False

    # LLM extraction flag from config (disk I/O)
    llm_enabled = False
    try:
        config_path = wiki_base / "config"
        config = await asyncio.to_thread(load_config, config_path)
        llm_enabled = config.daemon.daemon.features.llm_extraction
    except Exception:
        llm_enabled = False

    # Query log health from app state (set by lifespan startup)
    query_log_ok = not getattr(request.app.state, "query_log_error", False)

    return HealthResponse(
        daemon_running=daemon_running,
        index_loaded=index_loaded,
        scheduler_state=scheduler_state,
        llm_extraction_enabled=llm_enabled,
        query_log_ok=query_log_ok,
    )


@router.get("/daemon/status", response_model=DaemonStatusResponse)
async def daemon_status(wiki: WikiQuery = Depends(get_wiki)) -> DaemonStatusResponse:
    """Return daemon job schedules, last-run results, and next-run times."""
    store = JobExecutionStore(state_dir=wiki.wiki_base / "state")

    job_names: list[str] = await asyncio.to_thread(store.job_names)
    jobs: list[JobStatus] = []

    for job_name in job_names:
        history = await asyncio.to_thread(store.get_history, job_name)
        last = history.get_last()  # in-memory
        jobs.append(
            JobStatus(
                job_name=job_name,
                last_run=last.started_at.isoformat() if last else None,
                next_run=None,
                last_result=str(last.result) if last and last.result else None,
                status=last.status.value if last else "unknown",
            )
        )

    return DaemonStatusResponse(jobs=jobs)


@router.get("/daemon/jobs", response_model=list[IngestStatusResponse])
async def daemon_jobs(wiki: WikiQuery = Depends(get_wiki)) -> list[IngestStatusResponse]:
    """Return full job execution history."""
    store = JobExecutionStore(state_dir=wiki.wiki_base / "state")

    job_names: list[str] = await asyncio.to_thread(store.job_names)
    results: list[IngestStatusResponse] = []

    for job_name in job_names:
        history = await asyncio.to_thread(store.get_history, job_name)
        for exec_rec in history.executions:  # in-memory
            results.append(
                IngestStatusResponse(
                    job_id=exec_rec.execution_id,
                    status=exec_rec.status.value,
                    source_path=None,
                    domain=None,
                    page_ids=[],
                    indexed=(exec_rec.status == JobStatusEnum.COMPLETED),
                    message=exec_rec.error,
                )
            )

    return results
