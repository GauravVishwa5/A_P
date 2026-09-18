"""Prometheus metrics registry and telemetry collectors."""

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests processed",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request execution latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0),
)

# Domain Metrics
booking_attempts_total = Counter(
    "booking_attempts_total",
    "Total consultation booking attempts by result status",
    ["status"],  # success, conflict, error
)

payment_transactions_total = Counter(
    "payment_transactions_total",
    "Total payment processing attempts by status",
    ["status"],  # initiated, success, failed, refunded
)

auth_events_total = Counter(
    "auth_events_total",
    "Authentication lifecycle events counter",
    ["type"],  # login_success, login_failed, mfa_verified, token_refreshed, logout
)

# Infrastructure Metrics
db_pool_connections = Gauge(
    "db_pool_connections",
    "Active database pool connections",
    ["state"],  # active, idle, overflow
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database transaction duration in seconds",
    ["operation"],
    buckets=(0.002, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

redis_operations_total = Counter(
    "redis_operations_total",
    "Total Redis commands executed by status",
    ["command", "status"],
)


def get_metrics_content() -> tuple[bytes, str]:
    """Generate Prometheus metric scrape output and content-type."""
    return generate_latest(), CONTENT_TYPE_LATEST
