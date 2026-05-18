"""Unit tests for API error handling (ERROR_MAP and exception conversion)."""

from llm_wiki.api.errors import ERROR_MAP, wiki_error_to_http
from llm_wiki.exceptions import (
    DaemonNotRunningError,
    DomainUnknownError,
    ExportNotReadyError,
    IndexStaleError,
    IngestError,
    InvalidDepthError,
    QueryTimeoutError,
    WikiNotFoundError,
)


def test_wiki_not_found_maps_to_404():
    exc = WikiNotFoundError("page not found")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 404
    assert http_exc.detail["error_code"] == "WIKI_NOT_FOUND"
    assert http_exc.detail["rebuild_hint"] is False


def test_index_stale_has_rebuild_hint_true():
    exc = IndexStaleError("stale")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 503
    assert http_exc.detail["error_code"] == "INDEX_STALE"
    assert http_exc.detail["rebuild_hint"] is True


def test_domain_unknown_status_override_to_422():
    exc = DomainUnknownError("unknown domain")
    http_exc = wiki_error_to_http(exc, status_override=422)
    assert http_exc.status_code == 422
    assert http_exc.detail["error_code"] == "DOMAIN_UNKNOWN"


def test_query_timeout_error_not_in_error_map():
    assert QueryTimeoutError not in ERROR_MAP


def test_domain_unknown_default_404():
    exc = DomainUnknownError("domain xyz not configured")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 404


def test_ingest_error_422():
    exc = IngestError("bad ingest")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 422
    assert http_exc.detail["error_code"] == "INGEST_ERROR"


def test_daemon_not_running_503():
    exc = DaemonNotRunningError("daemon down")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 503


def test_export_not_ready_404():
    exc = ExportNotReadyError("export not ready")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 404


def test_invalid_depth_422():
    exc = InvalidDepthError("bad depth")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 422


def test_unknown_exception_defaults_to_500():
    exc = ValueError("unexpected")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.status_code == 500
    assert http_exc.detail["error_code"] == "INTERNAL_ERROR"


def test_rebuild_hint_only_for_index_stale():
    for exc_type, _ in ERROR_MAP.items():
        if exc_type is not IndexStaleError:
            http_exc = wiki_error_to_http(exc_type("test"))
            assert http_exc.detail["rebuild_hint"] is False
    # IndexStaleError specifically
    http_exc = wiki_error_to_http(IndexStaleError("test"))
    assert http_exc.detail["rebuild_hint"] is True


def test_message_field_preserved():
    exc = WikiNotFoundError("custom message")
    http_exc = wiki_error_to_http(exc)
    assert http_exc.detail["message"] == "custom message"
