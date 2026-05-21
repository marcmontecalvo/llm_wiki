"""OTel logging integration for LLW Wiki.

Integrates the OTel Python logging SDK with the existing daemon JSONFormatter.
The OTel logging handler injects ``trace_id`` and ``span_id`` into existing
structured log lines automatically — it does NOT replace the JSONFormatter.

The daemon's JSON formatter stays as-is for file logs; stdout integrates OTel
trace correlation so Grafana/Alloy LogQL can correlate logs with traces.
"""

from __future__ import annotations

import logging

from opentelemetry._logs import set_logger_provider

from llm_wiki.observability import sdk

_handler: logging.Handler | None = None


def setup_otel_logging() -> None:
    """Wire OTel logging into the root logger so all existing loggers propagate trace_id/span_id.

    The OTel LoggingHandler is attached as the primary handler on root logger.
    Existing formatters (e.g. JSONFormatter) can be added alongside it.
    """
    global _handler
    if _handler is not None:
        return

    provider = sdk._logger_provider
    if provider is None:
        return

    set_logger_provider(provider)
    _handler = sdk.get_logging_handler()
    root = logging.getLogger()
    root.addHandler(_handler)
