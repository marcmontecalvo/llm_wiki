"""Custom OTel metrics for the LLW Wiki service.

Provides counters, gauges, and helpers for observability data surfaced
to Grafana via OTLP exporters. Uses the ``llm_wiki`` meter namespace.

OTel SDK method names:
  - Counter.add(value)   (NOT .inc(), .increment())
  - Gauge.set(value)     (NOT .record())
  - Histogram.record(value, ...)
"""

from __future__ import annotations

from opentelemetry import metrics as metrics_api

# Counter: total number of query log write failures
query_log_write_failures_counter = metrics_api.get_meter("llm-wiki").create_counter(
    "query_log_write_failures_total",
    description="Total number of failed query log write operations",
)

# Gauge: query log initialization status (1=failure, 0=success)
query_log_init_failed_gauge = metrics_api.get_meter("llm-wiki").create_gauge(
    "wiki_query_log_init_failed",
    description="1 if QueryLogStore failed to initialize, 0 otherwise",
)

# Gauge: number of pages in the index
index_pages_gauge = metrics_api.get_meter("llm-wiki").create_gauge(
    "wiki_index_pages_total",
    description="Number of pages in the search index",
)


def set_init_failed(reason: str) -> None:
    """Set the init-failed gauge to 1 with the given reason label.

    Args:
        reason: Human-readable reason for the init failure.
    """
    query_log_init_failed_gauge.set(1.0, attributes={"reason": reason})
