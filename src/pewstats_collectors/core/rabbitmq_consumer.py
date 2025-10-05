"""RabbitMQ Consumer - Python AMQP implementation with R BaseWorker parity.

This module provides AMQP-based message consumption for pewstats workers.
Maintains full compatibility with R HTTP polling-based BaseWorker while using native AMQP.

Key features:
- Event-driven message consumption (replaces HTTP polling)
- Callback pattern matching R BaseWorker
- Auto-acknowledgment mode (R compatibility)
- Batch processing support
- Prefetch control for concurrency
- Graceful shutdown
"""

import json
import logging
import time
from typing import Any, Callable, Dict, Optional

import pika
from pika.exceptions import AMQPConnectionError


logger = logging.getLogger(__name__)


class RabbitMQConsumerError(Exception):
    """Custom exception for RabbitMQ consumer operations."""

    pass


class RabbitMQConsumer:
    """RabbitMQ consumer for PUBG match collection workers.

    Uses AMQP protocol (via pika) to consume messages from environment-specific queues.
    Replaces R BaseWorker HTTP polling with event-driven consumption.

    Callback contract (R compatibility):
        Input: Dict[str, Any] - Parsed message data
        Output: Dict[str, Any] - {"success": bool, "error": Optional[str]}

    Example:
        >>> def process_match(data: Dict[str, Any]) -> Dict[str, Any]:
        ...     match_id = data["match_id"]
        ...     # Process match...
        ...     return {"success": True}
        ...
        >>> consumer = RabbitMQConsumer(host="localhost", environment="prod")
        >>> consumer.consume_messages("match", "discovered", process_match)
    """

    def __init__(
        self,
        host: str,
        port: int = 5672,
        username: str = "guest",
        password: str = "guest",
        vhost: str = "/",
        environment: str = "prod",
        prefetch_count: int = 1,
        connection_timeout: int = 10,
        heartbeat: int = 600,
    ):
        """Initialize RabbitMQ consumer.

        Args:
            host: RabbitMQ host
            port: RabbitMQ AMQP port (default: 5672)
            username: RabbitMQ username
            password: RabbitMQ password
            vhost: RabbitMQ virtual host (default: "/")
            environment: Environment (prod, dev, etc.)
            prefetch_count: Number of messages to prefetch (default: 1)
            connection_timeout: Connection timeout in seconds
            heartbeat: Heartbeat interval in seconds

        Raises:
            RabbitMQConsumerError: If connection fails
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.vhost = vhost
        self.environment = environment
        self.prefetch_count = prefetch_count
        self.connection_timeout = connection_timeout
        self.heartbeat = heartbeat

        # Connection and channel (lazy initialization)
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None

        # Consumption state
        self._consuming = False
        self._processed_count = 0

        logger.info(
            f"RabbitMQ consumer initialized: {self.host}:{self.port} (vhost={self.vhost}, env={self.environment})"
        )

    def _build_queue_name(self, type: str, step: str) -> str:
        """Build environment-aware queue name.

        Format: {type}.{step}.{environment}

        Args:
            type: Message type (match, stats, telemetry, dlq)
            step: Processing step (discovered, processing, completed, failed)

        Returns:
            Queue name (e.g., "match.discovered.prod")
        """
        return f"{type}.{step}.{self.environment}"

    def _ensure_connection(self) -> None:
        """Ensure connection and channel are established.

        Creates connection and channel if they don't exist.

        Raises:
            RabbitMQConsumerError: If connection fails
        """
        if self._connection is None or self._connection.is_closed:
            try:
                credentials = pika.PlainCredentials(self.username, self.password)
                parameters = pika.ConnectionParameters(
                    host=self.host,
                    port=self.port,
                    virtual_host=self.vhost,
                    credentials=credentials,
                    connection_attempts=3,
                    retry_delay=2,
                    socket_timeout=self.connection_timeout,
                    heartbeat=self.heartbeat,
                )

                self._connection = pika.BlockingConnection(parameters)
                self._channel = self._connection.channel()

                # Set prefetch count (QoS)
                self._channel.basic_qos(prefetch_count=self.prefetch_count)

                logger.debug(f"Connected to RabbitMQ: {self.host}:{self.port}")

            except AMQPConnectionError as e:
                raise RabbitMQConsumerError(f"Failed to connect to RabbitMQ: {e}")

    def consume_messages(
        self,
        type: str,
        step: str,
        callback: Callable[[Dict[str, Any]], Dict[str, Any]],
        auto_ack: bool = True,
    ) -> None:
        """Start consuming messages from queue (daemon mode).

        Replaces R BaseWorker's start_polling method.
        Blocks indefinitely, processing messages as they arrive.

        Callback contract (R compatibility):
            Input: Parsed message dict
            Output: {"success": True/False, "error": optional error message}

        Args:
            type: Message type (match, stats, telemetry)
            step: Processing step (discovered, processing, completed, failed)
            callback: Function to process each message
            auto_ack: Auto-acknowledge messages (default: True for R compatibility)

        Raises:
            RabbitMQConsumerError: If consumption fails
        """
        try:
            self._ensure_connection()

            queue_name = self._build_queue_name(type, step)

            logger.info(f"Starting consumption from queue: {queue_name}")

            # Define message callback
            def on_message(channel, method, properties, body):
                self._on_message_callback(channel, method, properties, body, callback, auto_ack)

            # Start consuming
            self._channel.basic_consume(
                queue=queue_name, on_message_callback=on_message, auto_ack=auto_ack
            )

            self._consuming = True

            # Block and process messages
            logger.info(f"Waiting for messages from {queue_name}. Press Ctrl+C to exit.")
            self._channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("Consumption interrupted by user")
            self.stop_consuming()
        except Exception as e:
            logger.error(f"Error during consumption: {e}")
            raise RabbitMQConsumerError(f"Consumption failed: {e}")

    def consume_batch(
        self,
        type: str,
        step: str,
        callback: Callable[[Dict[str, Any]], Dict[str, Any]],
        max_messages: int = 10,
        auto_ack: bool = True,
    ) -> int:
        """Consume a batch of messages then stop (batch mode).

        Replaces R BaseWorker's processQueueMessages method.
        Processes up to max_messages then returns.

        Args:
            type: Message type
            step: Processing step
            callback: Function to process each message
            max_messages: Maximum number of messages to process
            auto_ack: Auto-acknowledge messages

        Returns:
            Number of messages successfully processed

        Raises:
            RabbitMQConsumerError: If consumption fails
        """
        try:
            self._ensure_connection()

            queue_name = self._build_queue_name(type, step)
            processed_count = 0

            logger.info(f"Processing batch from queue: {queue_name} (max={max_messages})")

            # Process messages one at a time
            for method_frame, properties, body in self._channel.consume(
                queue=queue_name, auto_ack=auto_ack, inactivity_timeout=1.0
            ):
                # Check for timeout (no more messages)
                if method_frame is None:
                    break

                # Process message
                result = self._process_message(body, callback)

                if result["success"]:
                    processed_count += 1

                # Manual ACK if not auto_ack
                if not auto_ack and method_frame:
                    if result["success"]:
                        self._channel.basic_ack(method_frame.delivery_tag)
                    else:
                        self._channel.basic_nack(method_frame.delivery_tag, requeue=False)

                # Stop if reached max
                if processed_count >= max_messages:
                    break

            # Cancel consumption
            self._channel.cancel()

            logger.info(
                f"Batch processing complete: {processed_count}/{max_messages} messages processed"
            )

            return processed_count

        except Exception as e:
            logger.error(f"Error during batch consumption: {e}")
            raise RabbitMQConsumerError(f"Batch consumption failed: {e}")

    def _on_message_callback(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
        callback: Callable[[Dict[str, Any]], Dict[str, Any]],
        auto_ack: bool,
    ) -> None:
        """Internal callback for processing messages.

        Handles message parsing, callback invocation, and acknowledgment.

        Args:
            channel: Pika channel
            method: Delivery method
            properties: Message properties
            body: Message body (JSON bytes)
            callback: User callback function
            auto_ack: Whether auto-ack is enabled
        """
        start_time = time.time()

        try:
            # Process message
            result = self._process_message(body, callback)

            # Track processing time
            processing_time = time.time() - start_time

            if result["success"]:
                self._processed_count += 1
                logger.debug(f"Successfully processed message in {processing_time:.2f}s")

                # Manual ACK if not auto_ack
                if not auto_ack:
                    channel.basic_ack(method.delivery_tag)
            else:
                logger.error(f"Message processing failed: {result.get('error', 'Unknown error')}")

                # Manual NACK if not auto_ack
                if not auto_ack:
                    channel.basic_nack(method.delivery_tag, requeue=False)

        except Exception as e:
            logger.error(f"Exception in message callback: {e}")

            # Manual NACK if not auto_ack
            if not auto_ack:
                channel.basic_nack(method.delivery_tag, requeue=False)

    def _process_message(
        self, body: bytes, callback: Callable[[Dict[str, Any]], Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process a single message.

        Parses JSON, calls callback, handles errors.

        Args:
            body: Message body (JSON bytes)
            callback: User callback function

        Returns:
            Result dict: {"success": bool, "error": Optional[str]}
        """
        try:
            # Parse JSON payload
            message_data = json.loads(body.decode("utf-8"))

            match_id = message_data.get("match_id", "unknown")
            logger.debug(f"Processing message for match: {match_id}")

            # Call user callback
            result = callback(message_data)

            # Validate result format
            if not isinstance(result, dict) or "success" not in result:
                logger.warning(f"Callback returned invalid format, treating as failure: {result}")
                return {"success": False, "error": "Invalid callback return format"}

            if result["success"]:
                logger.info(f"Successfully processed match: {match_id}")
            else:
                logger.error(
                    f"Failed to process match {match_id}: {result.get('error', 'Unknown error')}"
                )

            return result

        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse message JSON: {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"Exception during message processing: {e}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    def stop_consuming(self) -> None:
        """Stop consuming messages gracefully.

        Safe to call even if not consuming.
        """
        if self._consuming and self._channel and not self._channel.is_closed:
            try:
                self._channel.stop_consuming()
                self._consuming = False
                logger.info("Stopped consuming messages")
            except Exception as e:
                logger.warning(f"Error stopping consumption: {e}")

    def close(self) -> None:
        """Close RabbitMQ connection.

        Safe to call multiple times.
        """
        self.stop_consuming()

        if hasattr(self, "_channel") and self._channel and not self._channel.is_closed:
            try:
                self._channel.close()
            except Exception as e:
                logger.warning(f"Error closing channel: {e}")

        if hasattr(self, "_connection") and self._connection and not self._connection.is_closed:
            try:
                self._connection.close()
                logger.debug("RabbitMQ connection closed")
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")

    def get_processed_count(self) -> int:
        """Get number of messages processed.

        Returns:
            Count of successfully processed messages
        """
        return self._processed_count

    def __enter__(self):
        """Context manager entry."""
        self._ensure_connection()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Destructor - cleanup connection."""
        self.close()
