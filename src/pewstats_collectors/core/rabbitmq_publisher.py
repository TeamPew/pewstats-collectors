"""RabbitMQ Publisher - Python AMQP implementation with R parity.

This module provides AMQP-based message publishing for the pewstats-collectors service.
Maintains full compatibility with R HTTP API implementation while using native AMQP protocol.

Key features:
- Environment-aware queue/exchange naming ({type}.{step}.{env})
- AMQP protocol (via pika) for better performance
- Connection management with auto-reconnect
- Message persistence and durability
- Full R business logic parity
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import pika
from pika.exceptions import AMQPConnectionError


logger = logging.getLogger(__name__)


class RabbitMQError(Exception):
    """Custom exception for RabbitMQ operations."""

    pass


class RabbitMQPublisher:
    """RabbitMQ publisher for PUBG match collection system.

    Uses AMQP protocol (via pika) to publish messages to environment-specific queues.
    Maintains compatibility with R HTTP API implementation.

    Queue naming: {type}.{step}.{environment}
    Exchange naming: {type}.exchange.{environment}

    Example:
        >>> publisher = RabbitMQPublisher(host="localhost", environment="prod")
        >>> publisher.publish_message(
        ...     type="match",
        ...     step="discovered",
        ...     message={"match_id": "abc123", "timestamp": "2024-01-01"}
        ... )
        True
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: int = 5672,
        username: Optional[str] = None,
        password: Optional[str] = None,
        vhost: str = "/",
        environment: Optional[str] = None,
        connection_timeout: int = 10,
        heartbeat: int = 600,
    ):
        """Initialize RabbitMQ publisher.

        Args:
            host: RabbitMQ host (auto-detects from env if None)
            port: RabbitMQ AMQP port (default: 5672)
            username: RabbitMQ username (auto-detects from env if None)
            password: RabbitMQ password (auto-detects from env if None)
            vhost: RabbitMQ virtual host (default: "/")
            environment: Environment (prod, dev, etc.) (auto-detects if None)
            connection_timeout: Connection timeout in seconds
            heartbeat: Heartbeat interval in seconds

        Raises:
            RabbitMQError: If connection fails
        """
        # Parse configuration from environment
        config = self._parse_config(host, port, username, password, vhost, environment)

        self.host = config["host"]
        self.port = config["port"]
        self.username = config["username"]
        self.password = config["password"]
        self.vhost = config["vhost"]
        self.environment = config["environment"]
        self.connection_timeout = connection_timeout
        self.heartbeat = heartbeat

        # Connection and channel (lazy initialization)
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None

        logger.info(
            f"RabbitMQ publisher initialized: {self.host}:{self.port} (vhost={self.vhost}, env={self.environment})"
        )

    def _parse_config(
        self,
        host: Optional[str],
        port: int,
        username: Optional[str],
        password: Optional[str],
        vhost: str,
        environment: Optional[str],
    ) -> Dict[str, Any]:
        """Parse configuration from parameters and environment variables.

        Maintains R compatibility:
        - Checks for container environment (/.dockerenv or /run/.containerenv)
        - Uses RABBITMQ_CONTAINER_HOST if in container
        - Falls back to RABBITMQ_HOST otherwise
        - Auto-detects environment from ENVIRONMENT variable

        Args:
            host: Override host (None = auto-detect)
            port: AMQP port
            username: Override username (None = auto-detect)
            password: Override password (None = auto-detect)
            vhost: Virtual host
            environment: Override environment (None = auto-detect)

        Returns:
            Configuration dictionary

        Raises:
            RabbitMQError: If required configuration is missing
        """
        # Detect container environment (R compatibility)
        is_container = Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()

        # Parse host
        if host is None:
            if is_container and os.getenv("RABBITMQ_CONTAINER_HOST"):
                host = os.getenv("RABBITMQ_CONTAINER_HOST")
            else:
                host = os.getenv("RABBITMQ_HOST")

            if not host:
                raise RabbitMQError("RabbitMQ host is not set in environment")

        # Parse credentials
        if username is None:
            username = os.getenv("RABBITMQ_USER")
            if not username:
                raise RabbitMQError("RabbitMQ username is not set in environment")

        if password is None:
            password = os.getenv("RABBITMQ_PASSWORD")
            if not password:
                raise RabbitMQError("RabbitMQ password is not set in environment")

        # Parse port
        if port == 5672:  # Default not overridden
            env_port = os.getenv("RABBITMQ_PORT")
            if env_port:
                port = int(env_port)

        # Parse vhost
        env_vhost = os.getenv("RABBITMQ_VHOST")
        if env_vhost:
            vhost = env_vhost

        # Parse environment (default: "prod" like R)
        if environment is None:
            environment = os.getenv("ENVIRONMENT", "prod").lower()

        return {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "vhost": vhost,
            "environment": environment,
            "is_container": is_container,
        }

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

    def _build_exchange_name(self, type: str) -> str:
        """Build environment-aware exchange name.

        Format: {type}.exchange.{environment}

        Args:
            type: Message type (match, stats, telemetry)

        Returns:
            Exchange name (e.g., "match.exchange.prod")
        """
        return f"{type}.exchange.{self.environment}"

    def _ensure_connection(self) -> None:
        """Ensure connection and channel are established.

        Creates connection and channel if they don't exist.
        Raises:
            RabbitMQError: If connection fails
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

                logger.debug(f"Connected to RabbitMQ: {self.host}:{self.port}")

            except AMQPConnectionError as e:
                raise RabbitMQError(f"Failed to connect to RabbitMQ: {e}")

    def publish_message(
        self,
        type: str,
        step: str,
        message: Dict[str, Any],
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Publish message to RabbitMQ queue.

        Maintains R business logic:
        - Adds environment and queue_target to message
        - Uses default exchange ("") with routing_key = queue_name
        - Returns False on error (no exception raised)
        - Logs warnings on failure

        Args:
            type: Message type (match, stats, telemetry, dlq)
            step: Processing step (discovered, processing, completed, failed)
            message: Message payload (will be JSON serialized)
            properties: Optional message properties (e.g., content_type)

        Returns:
            True if message was published successfully, False otherwise
        """
        try:
            self._ensure_connection()

            # Build queue name (routing key)
            routing_key = self._build_queue_name(type, step)

            # Declare queue (idempotent - safe to call multiple times)
            # This ensures the queue exists before publishing
            self._channel.queue_declare(queue=routing_key, durable=True)

            # Add metadata to message (R compatibility)
            message_with_metadata = message.copy()
            message_with_metadata["environment"] = self.environment
            message_with_metadata["queue_target"] = routing_key

            # Serialize message to JSON
            payload = json.dumps(message_with_metadata)

            # Build AMQP properties
            amqp_properties = pika.BasicProperties(
                delivery_mode=2,  # Persistent message
                content_type=properties.get("content_type", "application/json")
                if properties
                else "application/json",
            )

            # Publish to default exchange with routing_key = queue_name
            # This matches R's behavior of publishing directly to queue
            self._channel.basic_publish(
                exchange="",  # Default exchange (R uses this)
                routing_key=routing_key,
                body=payload,
                properties=amqp_properties,
            )

            logger.debug(f"Published message to queue: {routing_key}")
            return True

        except Exception as e:
            logger.warning(f"Failed to publish message to {type}.{step}: {e}")
            return False

    def close(self) -> None:
        """Close RabbitMQ connection.

        Safe to call multiple times.
        """
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
