"""
Parallel Telemetry Processing Worker

Wraps TelemetryProcessingWorker with concurrent.futures for parallel processing.
Processes multiple telemetry files concurrently using a process pool.

Architecture:
- Main thread: RabbitMQ consumer (single-threaded, pika isn't thread-safe)
- Worker pool: ProcessPoolExecutor with N workers (CPU-bound tasks)
- Each worker process has its own database connection
"""

import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, Optional

from ..core.database_manager import DatabaseManager
from .telemetry_processing_worker import TelemetryProcessingWorker
from ..metrics import (
    QUEUE_MESSAGES_PROCESSED,
    QUEUE_PROCESSING_DURATION,
    start_metrics_server,
)


logger = logging.getLogger(__name__)


def _process_message_worker(
    message_data: Dict[str, Any],
    worker_id: str,
    db_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Worker function for processing a single message in a separate process.

    This function is executed in a child process by ProcessPoolExecutor.
    Each process gets its own database connection.

    Args:
        message_data: Message payload containing match_id and file_path
        worker_id: Worker identifier for logging
        db_config: Database configuration dict

    Returns:
        Result dict: {"success": bool, "error": Optional[str], "match_id": str}
    """
    try:
        # Create database manager for this process
        db_manager = DatabaseManager(
            host=db_config["host"],
            port=db_config["port"],
            dbname=db_config["dbname"],
            user=db_config["user"],
            password=db_config["password"],
            min_pool_size=1,
            max_pool_size=2,  # Small pool per worker
        )

        # Create worker instance
        worker = TelemetryProcessingWorker(
            database_manager=db_manager,
            worker_id=f"{worker_id}-pool",
            metrics_port=None,  # No metrics server in child processes
        )

        # Process message
        result = worker.process_message(message_data)

        # Clean up
        db_manager.disconnect()

        # Add match_id to result for tracking
        result["match_id"] = message_data.get("match_id")

        return result

    except Exception as e:
        error_msg = f"Worker process exception: {e}"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "match_id": message_data.get("match_id", "unknown"),
        }


class ParallelTelemetryProcessingWorker:
    """
    Parallel telemetry processing worker using ProcessPoolExecutor.

    Processes multiple telemetry files concurrently while maintaining
    single-threaded RabbitMQ consumption (pika requirement).

    Features:
    - Concurrent processing of multiple matches
    - Configurable worker pool size
    - Automatic database connection management per worker
    - Graceful shutdown with in-flight request handling
    """

    def __init__(
        self,
        worker_id: str,
        pool_size: int = 2,
        db_config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
        metrics_port: int = 9093,
    ):
        """
        Initialize parallel telemetry processing worker.

        Args:
            worker_id: Unique worker identifier
            pool_size: Number of worker processes (default: 2, should match CPU count)
            db_config: Database configuration dict (if None, reads from env)
            logger: Optional logger instance
            metrics_port: Port for Prometheus metrics server
        """
        self.worker_id = worker_id
        self.pool_size = pool_size
        self.logger = logger or logging.getLogger(__name__)

        # Database configuration (shared with worker processes)
        self.db_config = db_config or {
            "host": os.getenv("POSTGRES_HOST"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "dbname": os.getenv("POSTGRES_DB"),
            "user": os.getenv("POSTGRES_USER"),
            "password": os.getenv("POSTGRES_PASSWORD"),
        }

        # Initialize process pool
        self.executor = ProcessPoolExecutor(
            max_workers=self.pool_size,
            mp_context=None,  # Use default (fork on Linux, spawn on Windows)
        )

        # Processing counters
        self.processed_count = 0
        self.error_count = 0
        self.in_flight_count = 0

        # Track submitted futures
        self.futures = {}

        # Start metrics server
        start_metrics_server(port=metrics_port, worker_name=f"telemetry-processing-{worker_id}")

        self.logger.info(
            f"[{self.worker_id}] Parallel telemetry processing worker initialized "
            f"with {self.pool_size} worker processes"
        )

    def process_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a telemetry processing message (callback for RabbitMQConsumer).

        Submits the message to the process pool for concurrent processing.
        Waits for the result before returning to maintain RabbitMQ ack semantics.

        Args:
            data: Message payload containing match_id and file_path

        Returns:
            Dict with success status: {"success": bool, "error": str}
        """
        start_time = time.time()
        match_id = data.get("match_id", "unknown")

        try:
            # Submit to process pool
            future = self.executor.submit(
                _process_message_worker,
                data,
                self.worker_id,
                self.db_config,
            )

            self.in_flight_count += 1
            self.logger.debug(
                f"[{self.worker_id}] Submitted match {match_id} to worker pool "
                f"({self.in_flight_count} in-flight)"
            )

            # Wait for result (blocking to maintain RabbitMQ ack order)
            result = future.result()

            self.in_flight_count -= 1

            # Update counters
            if result.get("success"):
                self.processed_count += 1
                duration = time.time() - start_time
                QUEUE_MESSAGES_PROCESSED.labels(
                    queue_name="telemetry_processing", status="success"
                ).inc()
                QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(
                    duration
                )
                self.logger.info(
                    f"[{self.worker_id}] Successfully processed match {match_id} in {duration:.2f}s"
                )
            else:
                self.error_count += 1
                duration = time.time() - start_time
                QUEUE_MESSAGES_PROCESSED.labels(
                    queue_name="telemetry_processing", status="failed"
                ).inc()
                QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(
                    duration
                )
                self.logger.error(
                    f"[{self.worker_id}] Failed to process match {match_id}: "
                    f"{result.get('error', 'Unknown error')}"
                )

            return result

        except Exception as e:
            self.error_count += 1
            self.in_flight_count -= 1
            duration = time.time() - start_time
            error_msg = f"Exception processing match {match_id}: {e}"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            QUEUE_MESSAGES_PROCESSED.labels(
                queue_name="telemetry_processing", status="failed"
            ).inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name="telemetry_processing").observe(duration)
            return {"success": False, "error": error_msg}

    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the worker pool gracefully.

        Args:
            wait: Whether to wait for in-flight tasks to complete
        """
        self.logger.info(
            f"[{self.worker_id}] Shutting down worker pool "
            f"(wait={wait}, in-flight={self.in_flight_count})"
        )

        self.executor.shutdown(wait=wait)

        self.logger.info(
            f"[{self.worker_id}] Worker pool shut down. "
            f"Processed: {self.processed_count}, Errors: {self.error_count}"
        )

    def __del__(self):
        """Destructor - ensure pool is shutdown."""
        try:
            self.shutdown(wait=False)
        except Exception:
            pass


if __name__ == "__main__":
    from pewstats_collectors.core.rabbitmq_consumer import RabbitMQConsumer

    # Configure logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Get worker pool size from environment (default: 2, should match CPU count)
    pool_size = int(os.getenv("WORKER_POOL_SIZE", "2"))

    # Initialize parallel worker
    worker = ParallelTelemetryProcessingWorker(
        worker_id=os.getenv("WORKER_ID", "telemetry-processing-worker-1"),
        pool_size=pool_size,
    )

    # Initialize consumer
    consumer = RabbitMQConsumer(
        host=os.getenv("RABBITMQ_HOST"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment=os.getenv("ENVIRONMENT", "development"),
        prefetch_count=pool_size,  # Prefetch matches pool size
    )

    # Start consuming
    print(f"Starting parallel telemetry processing worker: {worker.worker_id}")
    print(f"Worker pool size: {pool_size} processes")
    try:
        consumer.consume_messages("match", "processing", worker.process_message)
    except KeyboardInterrupt:
        print("\nShutting down...")
        worker.shutdown(wait=True)
        consumer.close()
