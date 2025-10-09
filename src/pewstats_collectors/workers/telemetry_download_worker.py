"""
Telemetry Download Worker

Downloads telemetry JSON files from PUBG CDN and stores them locally as compressed files.
"""

import gzip
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

from ..core.rabbitmq_publisher import RabbitMQPublisher
from ..metrics import (
    TELEMETRY_DOWNLOADS,
    TELEMETRY_DOWNLOAD_DURATION,
    TELEMETRY_FILE_SIZE,
    QUEUE_MESSAGES_PROCESSED,
    QUEUE_PROCESSING_DURATION,
    WORKER_ERRORS,
    start_metrics_server,
)


class TelemetryDownloadWorker:
    """
    Worker that downloads telemetry JSON files from CDN.

    Responsibilities:
    - Download telemetry JSON from CDN URL
    - Compress and store locally
    - Publish to telemetry processing queue
    """

    def __init__(
        self,
        rabbitmq_publisher: RabbitMQPublisher,
        worker_id: str,
        data_path: str = "/opt/pewstats-platform/data/telemetry",
        logger: Optional[logging.Logger] = None,
        metrics_port: int = 9092,
    ):
        """
        Initialize telemetry download worker.

        Args:
            rabbitmq_publisher: RabbitMQ publisher instance
            worker_id: Unique worker identifier
            data_path: Path to store telemetry files
            logger: Optional logger instance
            metrics_port: Port to expose Prometheus metrics on (default: 9092)
        """
        self.rabbitmq_publisher = rabbitmq_publisher
        self.worker_id = worker_id
        self.data_path = data_path
        self.logger = logger or logging.getLogger(__name__)

        # Processing counters
        self.processed_count = 0
        self.error_count = 0

        # Create data directory
        os.makedirs(self.data_path, exist_ok=True)

        # Start metrics server
        start_metrics_server(port=metrics_port, worker_name=f"telemetry-download-{worker_id}")

        self.logger.info(
            f"[{self.worker_id}] Telemetry download worker initialized with data path: {self.data_path}"
        )

    def process_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a telemetry download message (callback for RabbitMQConsumer).

        Args:
            data: Message payload containing match_id and telemetry_url

        Returns:
            Dict with success status: {"success": bool, "error": str}
        """
        start_time = time.time()
        match_id = data.get("match_id")
        telemetry_url = data.get("telemetry_url")

        if not match_id:
            error_msg = "Message missing match_id field"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            self.error_count += 1
            QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_download', status='failed').inc()
            return {"success": False, "error": error_msg}

        if not telemetry_url:
            error_msg = f"Message missing telemetry_url field for match {match_id}"
            self.logger.error(f"[{self.worker_id}] {error_msg}")
            self.error_count += 1
            QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_download', status='failed').inc()
            return {"success": False, "error": error_msg}

        self.logger.info(f"[{self.worker_id}] Processing telemetry download for match: {match_id}")
        self.logger.debug(f"[{self.worker_id}] Telemetry URL: {telemetry_url[:80]}...")

        try:
            # Check if telemetry already downloaded (idempotency)
            if self.telemetry_exists(match_id):
                self.logger.info(
                    f"[{self.worker_id}] Telemetry already exists for {match_id}, "
                    "forwarding to processing queue"
                )

                # Get file info for message
                file_path = self._get_file_path(match_id)
                file_size_mb = os.path.getsize(file_path) / (1024**2)

                # Still publish to processing queue
                publish_success = self._publish_processing_message(
                    match_id, data, file_path, file_size_mb
                )

                if publish_success:
                    self.processed_count += 1
                    TELEMETRY_DOWNLOADS.labels(status='cached').inc()
                    TELEMETRY_FILE_SIZE.observe(os.path.getsize(file_path))
                    QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_download', status='success').inc()
                    QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_download').observe(time.time() - start_time)
                    return {"success": True, "reason": "already_exists"}
                else:
                    error_msg = "Failed to publish to processing queue"
                    self.logger.error(f"[{self.worker_id}] {error_msg}")
                    self.error_count += 1
                    TELEMETRY_DOWNLOADS.labels(status='failed').inc()
                    QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_download', status='failed').inc()
                    WORKER_ERRORS.labels(worker_type='telemetry_download', error_type='PublishError').inc()
                    return {"success": False, "error": error_msg}

            # Download telemetry
            download_start = time.time()
            download_result = self.download_telemetry(telemetry_url, match_id)
            download_elapsed = time.time() - download_start

            file_size_mb = download_result["size_mb"]
            file_size_bytes = int(file_size_mb * 1024 * 1024)
            self.logger.info(
                f"[{self.worker_id}] Downloaded telemetry for {match_id}: "
                f"{file_size_mb:.2f} MB in {download_elapsed:.2f}s"
            )

            # Record download metrics
            TELEMETRY_DOWNLOAD_DURATION.observe(download_elapsed)
            TELEMETRY_FILE_SIZE.observe(file_size_bytes)

            # Publish to processing queue
            file_path = download_result["file_path"]
            publish_success = self._publish_processing_message(
                match_id, data, file_path, file_size_mb
            )

            if not publish_success:
                error_msg = "Failed to publish to processing queue"
                self.logger.error(f"[{self.worker_id}] {error_msg}")
                self.error_count += 1
                return {"success": False, "error": error_msg}

            # Success!
            self.processed_count += 1
            total_duration = time.time() - start_time
            self.logger.info(
                f"[{self.worker_id}] ✅ Successfully downloaded and queued telemetry for {match_id}"
            )

            # Record success metrics
            TELEMETRY_DOWNLOADS.labels(status='success').inc()
            QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_download', status='success').inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_download').observe(total_duration)

            return {"success": True}

        except Exception as e:
            total_duration = time.time() - start_time
            error_msg = f"Telemetry download failed: {str(e)}"
            self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}", exc_info=True)
            self.error_count += 1

            # Record error metrics
            TELEMETRY_DOWNLOADS.labels(status='failed').inc()
            QUEUE_MESSAGES_PROCESSED.labels(queue_name='telemetry_download', status='failed').inc()
            QUEUE_PROCESSING_DURATION.labels(queue_name='telemetry_download').observe(total_duration)
            WORKER_ERRORS.labels(worker_type='telemetry_download', error_type=type(e).__name__).inc()

            return {"success": False, "error": str(e)}

    def download_telemetry(
        self, telemetry_url: str, match_id: str, max_attempts: int = 3
    ) -> Dict[str, Any]:
        """
        Download telemetry JSON from CDN with retry logic.

        Args:
            telemetry_url: CDN URL to download from
            match_id: Match ID for file organization
            max_attempts: Maximum download attempts

        Returns:
            Dict with file_path and size_mb

        Raises:
            Exception: If download fails after all retries
        """
        # Create match directory
        match_dir = os.path.join(self.data_path, f"matchID={match_id}")
        os.makedirs(match_dir, exist_ok=True)

        final_path = os.path.join(match_dir, "raw.json.gz")

        for attempt in range(1, max_attempts + 1):
            tmp_path = None
            try:
                self.logger.debug(
                    f"[{self.worker_id}] Match {match_id}: Downloading telemetry "
                    f"(attempt {attempt}/{max_attempts})"
                )

                # Create temp file
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
                os.close(tmp_fd)  # Close fd, we'll use path

                # Download with streaming
                response = requests.get(
                    telemetry_url,
                    stream=True,
                    timeout=120,  # 2 minutes
                )
                response.raise_for_status()

                # Write to temp file
                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                # Validate download
                if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                    raise ValueError("Downloaded file is empty or missing")

                file_size = os.path.getsize(tmp_path)
                self.logger.debug(
                    f"[{self.worker_id}] Match {match_id}: Downloaded {file_size / (1024**2):.2f} MB"
                )

                # Handle compression
                if telemetry_url.endswith(".gz") or is_gzipped(tmp_path):
                    # Already gzipped, just move
                    shutil.move(tmp_path, final_path)
                    self.logger.debug(f"[{self.worker_id}] Match {match_id}: File already gzipped")
                else:
                    # Compress it
                    with open(tmp_path, "rb") as f_in:
                        with gzip.open(final_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.remove(tmp_path)
                    self.logger.debug(f"[{self.worker_id}] Match {match_id}: Compressed file")

                # Verify final file
                if not os.path.exists(final_path):
                    raise ValueError("Final file not created")

                final_size_mb = os.path.getsize(final_path) / (1024**2)

                return {
                    "file_path": final_path,
                    "size_mb": final_size_mb,
                }

            except Exception as e:
                # Clean up temp file
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass

                if attempt == max_attempts:
                    error_msg = (
                        f"Failed to download telemetry after {max_attempts} attempts: {str(e)}"
                    )
                    self.logger.error(f"[{self.worker_id}] Match {match_id}: {error_msg}")
                    raise Exception(error_msg)

                # Exponential backoff
                wait_time = 2**attempt
                self.logger.warning(
                    f"[{self.worker_id}] Match {match_id}: Download attempt {attempt} failed, "
                    f"retrying in {wait_time}s: {str(e)}"
                )
                time.sleep(wait_time)

        # Should never reach here
        raise Exception("Download failed unexpectedly")

    def telemetry_exists(self, match_id: str) -> bool:
        """
        Check if telemetry file already exists.

        Args:
            match_id: Match ID to check

        Returns:
            True if file exists, False otherwise
        """
        file_path = self._get_file_path(match_id)
        exists = os.path.exists(file_path)

        if exists:
            self.logger.debug(f"[{self.worker_id}] Telemetry file exists for match {match_id}")

        return exists

    def get_stats(self) -> Dict[str, Any]:
        """
        Get worker statistics.

        Returns:
            Dictionary with worker stats
        """
        total = self.processed_count + self.error_count
        success_rate = self.processed_count / total if total > 0 else 0

        return {
            "worker_id": self.worker_id,
            "worker_type": "TelemetryDownloadWorker",
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "success_rate": success_rate,
            "data_path": self.data_path,
            "last_check": datetime.now(timezone.utc).isoformat(),
        }

    def _get_file_path(self, match_id: str) -> str:
        """Get file path for match telemetry"""
        return os.path.join(self.data_path, f"matchID={match_id}", "raw.json.gz")

    def _publish_processing_message(
        self,
        match_id: str,
        original_data: Dict[str, Any],
        file_path: str,
        file_size_mb: float,
    ) -> bool:
        """
        Publish message to telemetry processing queue.

        Args:
            match_id: Match ID
            original_data: Original message data
            file_path: Path to downloaded file
            file_size_mb: File size in MB

        Returns:
            True if published successfully
        """
        message = {
            "match_id": match_id,
            "file_path": file_path,
            "file_size_mb": file_size_mb,
            "map_name": original_data.get("map_name"),
            "game_mode": original_data.get("game_mode"),
            "match_datetime": original_data.get("match_datetime"),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "worker_id": self.worker_id,
        }

        success = self.rabbitmq_publisher.publish_message("match", "processing", message)

        if success:
            self.logger.debug(
                f"[{self.worker_id}] Published processing message for match {match_id}"
            )
        else:
            self.logger.warning(
                f"[{self.worker_id}] Failed to publish processing message for match {match_id}"
            )

        return success


# Helper functions


def is_gzipped(file_path: str) -> bool:
    """
    Check if file is gzipped using magic number.

    Args:
        file_path: Path to file

    Returns:
        True if file is gzipped
    """
    try:
        with open(file_path, "rb") as f:
            magic = f.read(2)
        return magic == b"\x1f\x8b"
    except (IOError, OSError):
        return False


if __name__ == "__main__":
    import os
    from pewstats_collectors.core.rabbitmq_consumer import RabbitMQConsumer

    # Configure logging
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize RabbitMQ publisher
    rabbitmq_publisher = RabbitMQPublisher()

    # Initialize worker
    worker = TelemetryDownloadWorker(
        rabbitmq_publisher=rabbitmq_publisher,
        data_path=os.getenv("TELEMETRY_STORAGE_PATH", "/opt/pewstats-platform/data/telemetry"),
        worker_id=os.getenv("WORKER_ID", "telemetry-download-worker-1"),
    )

    # Initialize consumer
    consumer = RabbitMQConsumer(
        host=os.getenv("RABBITMQ_HOST"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment=os.getenv("ENVIRONMENT", "development"),
    )

    # Start consuming
    print(f"Starting telemetry download worker: {worker.worker_id}")
    consumer.consume_messages("match", "telemetry", worker.process_message)
