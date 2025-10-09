"""
Prometheus metrics for collectors workers
"""

from prometheus_client import Counter, Histogram, Gauge, Info, start_http_server
import logging

logger = logging.getLogger(__name__)

# Match discovery metrics
MATCH_DISCOVERY_REQUESTS = Counter(
    "match_discovery_requests_total",
    "Total PUBG API requests for match discovery",
    ["status"],  # success, failed
)

MATCH_DISCOVERY_RUNS = Counter(
    "match_discovery_runs_total",
    "Total match discovery pipeline runs",
    ["status"],  # success, failed
)

MATCH_DISCOVERY_DURATION = Histogram(
    "match_discovery_duration_seconds",
    "Time to complete match discovery pipeline",
    buckets=[10, 30, 60, 120, 300, 600, 1200, 1800],
)

MATCHES_DISCOVERED = Counter(
    "matches_discovered_total",
    "Total matches discovered",
    ["status"],  # new, existing, failed
)

MATCHES_QUEUED = Counter(
    "matches_queued_total",
    "Total matches queued for processing",
    ["status"],  # success, failed
)

ACTIVE_PLAYERS_COUNT = Gauge("active_players_count", "Number of active players being tracked")

# Match summary worker metrics
MATCH_SUMMARIES_PROCESSED = Counter(
    "match_summaries_processed_total",
    "Total match summaries processed",
    ["status"],  # success, failed, skipped
)

MATCH_PROCESSING_DURATION = Histogram(
    "match_processing_duration_seconds",
    "Time to process a match summary",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

# Telemetry download worker metrics
TELEMETRY_DOWNLOADS = Counter(
    "telemetry_downloads_total",
    "Total telemetry files downloaded",
    ["status"],  # success, failed, cached
)

TELEMETRY_DOWNLOAD_DURATION = Histogram(
    "telemetry_download_duration_seconds",
    "Time to download telemetry file",
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

TELEMETRY_FILE_SIZE = Histogram(
    "telemetry_file_size_bytes",
    "Size of downloaded telemetry files",
    buckets=[100_000, 500_000, 1_000_000, 5_000_000, 10_000_000, 50_000_000],
)

# Telemetry processing worker metrics
TELEMETRY_PROCESSED = Counter(
    "telemetry_processed_total",
    "Total telemetry files processed",
    ["status"],  # success, failed, skipped
)

TELEMETRY_PROCESSING_DURATION = Histogram(
    "telemetry_processing_duration_seconds",
    "Time to process telemetry file",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800],
)

TELEMETRY_EVENTS_EXTRACTED = Counter(
    "telemetry_events_extracted_total",
    "Total events extracted from telemetry",
    ["event_type"],  # LogPlayerKill, LogPlayerTakeDamage, etc.
)

# Queue metrics
QUEUE_MESSAGES_PROCESSED = Counter(
    "queue_messages_processed_total",
    "Total messages processed from queue",
    ["queue_name", "status"],  # success, failed, rejected
)

QUEUE_PROCESSING_DURATION = Histogram(
    "queue_processing_duration_seconds",
    "Time to process a message from queue",
    ["queue_name"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
)

# Worker health and errors
WORKER_INFO = Info("worker", "Worker information")

WORKER_ERRORS = Counter("worker_errors_total", "Total worker errors", ["worker_type", "error_type"])

WORKER_RESTARTS = Counter(
    "worker_restarts_total", "Total worker restarts", ["worker_type", "reason"]
)

# Database operations
DATABASE_OPERATIONS = Counter(
    "database_operations_total",
    "Total database operations",
    ["operation", "table", "status"],  # operation: insert, update, select; status: success, failed
)

DATABASE_OPERATION_DURATION = Histogram(
    "database_operation_duration_seconds",
    "Duration of database operations",
    ["operation", "table"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10, 30],
)

DATABASE_CONNECTION_POOL_SIZE = Gauge(
    "database_connection_pool_size", "Current number of connections in pool", ["pool_name"]
)

# API rate limiting
API_RATE_LIMIT_REMAINING = Gauge(
    "pubg_api_rate_limit_remaining", "Remaining PUBG API rate limit", ["endpoint"]
)

API_RATE_LIMIT_RESETS_AT = Gauge(
    "pubg_api_rate_limit_resets_at", "Unix timestamp when PUBG API rate limit resets", ["endpoint"]
)

# Business metrics
MATCHES_IN_DATABASE = Gauge("matches_in_database_total", "Total number of matches in database")

TELEMETRY_FILES_IN_DATABASE = Gauge(
    "telemetry_files_in_database_total", "Total number of telemetry files in database"
)


def start_metrics_server(port: int = 9090, worker_name: str = "unknown"):
    """
    Start the Prometheus metrics HTTP server

    Args:
        port: Port to expose metrics on
        worker_name: Name/type of the worker for logging and info metric
    """
    try:
        WORKER_INFO.info({"worker_name": worker_name, "metrics_port": str(port)})
        start_http_server(port)
        logger.info(f"Metrics server started on port {port} for worker: {worker_name}")
    except OSError as e:
        if e.errno == 98:  # Address already in use
            logger.warning(f"Metrics server port {port} already in use, skipping startup")
        else:
            logger.error(f"Failed to start metrics server on port {port}: {e}")
            raise
