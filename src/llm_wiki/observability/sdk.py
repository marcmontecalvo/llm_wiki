"""OpenTelemetry SDK initialization for the LLW Wiki service.

Configures TracerProvider, MeterProvider, and LoggerProvider with OTLP exporters.
All configuration is driven by environment variables (OTEL_*).
If exporters fail to connect, the SDK falls back to no-op silently.
"""

from __future__ import annotations

import logging
import os

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from llm_wiki import __version__

logger = logging.getLogger(__name__)

_resource: Resource | None = None
_trace_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None
_logger_provider: LoggerProvider | None = None


def _make_resource() -> Resource:
    return Resource.create(
        {"service.name": "llm-wiki", "service.version": __version__},
    )


def _get_exporter_protocol() -> str | None:
    """Return the OTLP protocol from OTEL_EXPORTER_OTLP_PROTOCOL env var, or None."""
    return os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL")


def initialize() -> None:
    """Initialize the OpenTelemetry SDK.

    Creates TracerProvider, MeterProvider, and LoggerProvider configured
    with OTLP exporters. Uses env vars for configuration:
      - OTEL_EXPORTER_OTLP_PROTOCOL (grpc or http)
      - OTEL_EXPORTER_OTLP_TIMEOUT
      - OTEL_EXPORTER_OTLP_ENDPOINT

    If exporters fail to connect, the SDK silently buffers then drops --
    never raises an exception to the caller.
    """
    global _resource, _trace_provider, _meter_provider, _logger_provider

    if _trace_provider is not None:
        return  # Already initialized

    _resource = _make_resource()

    # Tracing -- OTLP exporter with BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as GRPCTraceExporter,
    )
    proc = BatchSpanProcessor(GRPCTraceExporter())
    _trace_provider = TracerProvider(resource=_resource)
    _trace_provider.add_span_processor(proc)

    # Metrics -- PeriodicExportingMetricReader with OTLP metric exporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter as GRPCCMetricExporter,
    )
    reader = PeriodicExportingMetricReader(GRPCCMetricExporter())
    _meter_provider = MeterProvider(resource=_resource, metric_readers=[reader])

    # Logging -- LoggerProvider with OTel LoggingHandler
    _logger_provider = LoggerProvider(resource=_resource)

    logger.debug("OpenTelemetry SDK initialized (traces, metrics, logs)")


def shutdown() -> None:
    """Flush and shut down all OTel providers."""
    if _trace_provider is not None:
        _trace_provider.shutdown()
    if _meter_provider is not None:
        _meter_provider.shutdown()
    if _logger_provider is not None:
        _logger_provider.shutdown()
    logger.debug("OpenTelemetry SDK shut down")


def get_tracer() -> "opentelemetry.trace.Tracer  # type: ignore[name-defined]":  # noqa: F821
    """Return the configured tracer, or a no-op tracer if SDK is not initialized."""
    if _trace_provider is not None:
        return _trace_provider.get_tracer("llm-wiki")
    from opentelemetry.trace import get_tracer

    return get_tracer()


def get_meter():
    """Return the configured meter, or a no-op meter if SDK is not initialized."""
    if _meter_provider is not None:
        return _meter_provider.get_meter("llm-wiki")
    from opentelemetry.metrics import get_meter

    return get_meter()


def get_logging_handler() -> LoggingHandler:
    """Return the LoggingHandler for injecting trace_id/span_id into log records."""
    if _logger_provider is not None:
        return LoggingHandler(level=logging.NOTSET, logger_provider=_logger_provider)
    # Fall back to no-op handler if logger not initialized
    return LoggingHandler(level=logging.NOTSET)
