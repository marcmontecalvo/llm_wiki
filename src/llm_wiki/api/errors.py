"""Explicit error routing — ERROR_MAP and exception handlers.

Maps WikiError subclasses to FastAPI HTTPException values.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from llm_wiki.exceptions import (
    DaemonNotRunningError,
    DomainUnknownError,
    ExportNotReadyError,
    FactConflictError,
    IndexStaleError,
    IngestError,
    InvalidDepthError,
    UnknownFactCategoryError,
    UnknownFactKeyError,
    WikiNotFoundError,
)

ERROR_MAP: dict[type, tuple[int, str]] = {
    WikiNotFoundError: (404, "WIKI_NOT_FOUND"),
    DomainUnknownError: (404, "DOMAIN_UNKNOWN"),
    IngestError: (422, "INGEST_ERROR"),
    IndexStaleError: (503, "INDEX_STALE"),
    DaemonNotRunningError: (503, "DAEMON_NOT_RUNNING"),
    ExportNotReadyError: (404, "EXPORT_NOT_READY"),
    InvalidDepthError: (422, "INVALID_DEPTH"),
    UnknownFactCategoryError: (422, "UNKNOWN_KNOWLEDGE_CATEGORY"),
    UnknownFactKeyError: (404, "UNKNOWN_FACT_KEY"),
    FactConflictError: (409, "FACT_CONFLICT"),
}
# QueryTimeoutError is intentionally absent — it is a normal response branch


def wiki_error_to_http(
    exc: Exception,
    status_override: int | None = None,
) -> HTTPException:
    """Convert a WikiError to a FastAPI HTTPException.

    Args:
        exc: The exception to convert.
        status_override: Optional HTTP status code override.

    Returns:
        An HTTPException with appropriate status and detail.
    """
    for exc_type, (status, error_code) in ERROR_MAP.items():
        if isinstance(exc, exc_type):
            if status_override is not None:
                status = status_override
            rebuild_hint = isinstance(exc, IndexStaleError)
            return HTTPException(
                status_code=status,
                detail={
                    "error_code": error_code,
                    "message": str(exc),
                    "rebuild_hint": rebuild_hint,
                },
            )
    # Fallback for unknown exceptions
    return HTTPException(
        status_code=500,
        detail={
            "error_code": "INTERNAL_ERROR",
            "message": str(exc),
            "rebuild_hint": False,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI app.

    Handles both FastAPI HTTPException and manual WikiError raises via
    ``raise HTTPException(...)`` (which is what wiki_error_to_http returns).

    Args:
        app: The FastAPI application to attach handlers to.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if exc.detail is not None else {}
        if "error_code" not in detail:
            detail = {"error_code": "HTTP_ERROR", "message": str(exc.detail), "rebuild_hint": False}
        return JSONResponse(
            status_code=exc.status_code,
            content=detail,
            headers=exc.headers,
        )

    @app.exception_handler(WikiNotFoundError)
    async def wiki_not_found_handler(request: Request, exc: WikiNotFoundError) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(DomainUnknownError)
    async def domain_unknown_handler(request: Request, exc: DomainUnknownError) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(IngestError)
    async def ingest_error_handler(request: Request, exc: IngestError) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(IndexStaleError)
    async def index_stale_handler(request: Request, exc: IndexStaleError) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(DaemonNotRunningError)
    async def daemon_not_running_handler(
        request: Request, exc: DaemonNotRunningError
    ) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(ExportNotReadyError)
    async def export_not_ready_handler(request: Request, exc: ExportNotReadyError) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(InvalidDepthError)
    async def invalid_depth_handler(request: Request, exc: InvalidDepthError) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(UnknownFactCategoryError)
    async def unknown_fact_category_handler(
        request: Request, exc: UnknownFactCategoryError
    ) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        detail = http_exc.detail if isinstance(http_exc.detail, dict) else {}
        detail["details"] = {"category": exc.category, "valid_categories": exc.valid_categories}
        return JSONResponse(
            status_code=http_exc.status_code,
            content=detail,
        )

    @app.exception_handler(UnknownFactKeyError)
    async def unknown_fact_key_handler(request: Request, exc: UnknownFactKeyError) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )

    @app.exception_handler(FactConflictError)
    async def fact_conflict_handler(request: Request, exc: FactConflictError) -> JSONResponse:
        http_exc = wiki_error_to_http(exc)
        return JSONResponse(
            status_code=http_exc.status_code,
            content=http_exc.detail,
        )
