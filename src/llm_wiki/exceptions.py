"""Canonical WikiError exception hierarchy.

All custom wiki exceptions must inherit from WikiError and end in Error
(to satisfy Ruff N818). Each subclass maps to a specific HTTP status code
via ERROR_MAP in api/errors.py.
"""

__all__ = [
    "WikiError",
    "WikiNotFoundError",
    "DomainUnknownError",
    "IngestError",
    "IndexStaleError",
    "DaemonNotRunningError",
    "ExportNotReadyError",
    "InvalidDepthError",
    "QueryTimeoutError",
]


class WikiError(Exception):
    """Base class for all wiki-specific exceptions."""


class WikiNotFoundError(WikiError):
    """Raised when a requested page or resource does not exist."""


class DomainUnknownError(WikiError):
    """Raised when a domain is not configured or recognized."""


class IngestError(WikiError):
    """Raised when an ingestion step fails irrecoverably."""


class IndexStaleError(WikiError):
    """Raised when an index is detected to be stale and needs rebuilding."""


class DaemonNotRunningError(WikiError):
    """Raised when the daemon is expected to be running but is not."""


class ExportNotReadyError(WikiError):
    """Raised when an export is not yet ready for retrieval."""


class InvalidDepthError(WikiError):
    """Raised when an invalid depth parameter is supplied."""


class QueryTimeoutError(WikiError):
    """Raised when a deep query exceeds its timeout.

    This exception is intentionally NOT included in ERROR_MAP because
    it represents a normal response branch, not an HTTP error. The caller
    should return partial results with timed_out=True.
    """
