"""Unit tests for RabbitMQPublisher.

Tests AMQP-based publishing with mocked pika connections.
Ensures R business logic parity.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher, RabbitMQError


@pytest.fixture
def mock_connection():
    """Mock pika connection and channel."""
    connection = Mock()
    channel = Mock()
    connection.is_closed = False
    channel.is_closed = False
    connection.channel.return_value = channel
    return connection, channel


@pytest.fixture
def publisher(mock_connection):
    """Create RabbitMQPublisher with mocked connection."""
    conn, channel = mock_connection

    with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection', return_value=conn):
        with patch.dict('os.environ', {
            'RABBITMQ_HOST': 'localhost',
            'RABBITMQ_USER': 'test_user',
            'RABBITMQ_PASSWORD': 'test_pass',
            'ENVIRONMENT': 'dev'
        }):
            pub = RabbitMQPublisher()
            yield pub, channel


# ============================================================================
# Initialization Tests
# ============================================================================

class TestRabbitMQPublisherInitialization:
    """Test publisher initialization."""

    def test_initialization_from_env_variables(self):
        """Test initialization using environment variables."""
        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection'):
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'rabbitmq.example.com',
                'RABBITMQ_PORT': '5673',
                'RABBITMQ_USER': 'pubg_service',
                'RABBITMQ_PASSWORD': 'secret123',
                'RABBITMQ_VHOST': '/pubg',
                'ENVIRONMENT': 'prod'
            }):
                pub = RabbitMQPublisher()

                assert pub.host == 'rabbitmq.example.com'
                assert pub.port == 5673
                assert pub.username == 'pubg_service'
                assert pub.password == 'secret123'
                assert pub.vhost == '/pubg'
                assert pub.environment == 'prod'

    def test_initialization_with_explicit_parameters(self):
        """Test initialization with explicit parameters."""
        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection'):
            with patch.dict('os.environ', {}, clear=True):
                pub = RabbitMQPublisher(
                    host='custom.host',
                    port=5555,
                    username='custom_user',
                    password='custom_pass',
                    vhost='/custom',
                    environment='staging'
                )

                assert pub.host == 'custom.host'
                assert pub.port == 5555
                assert pub.username == 'custom_user'
                assert pub.password == 'custom_pass'
                assert pub.vhost == '/custom'
                assert pub.environment == 'staging'

    def test_initialization_missing_host(self):
        """Test initialization fails with missing host."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(RabbitMQError, match="RabbitMQ host is not set"):
                RabbitMQPublisher()

    def test_initialization_missing_credentials(self):
        """Test initialization fails with missing credentials."""
        with patch.dict('os.environ', {'RABBITMQ_HOST': 'localhost'}, clear=True):
            with pytest.raises(RabbitMQError, match="username is not set"):
                RabbitMQPublisher()

    def test_container_environment_detection(self):
        """Test container environment detection (R compatibility)."""
        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection'):
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'host_value',
                'RABBITMQ_CONTAINER_HOST': 'container_value',
                'RABBITMQ_USER': 'user',
                'RABBITMQ_PASSWORD': 'pass'
            }):
                # Simulate container environment
                with patch('pewstats_collectors.core.rabbitmq_publisher.Path.exists', return_value=True):
                    pub = RabbitMQPublisher()
                    assert pub.host == 'container_value'

    def test_host_environment_detection(self):
        """Test host (non-container) environment detection."""
        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection'):
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'host_value',
                'RABBITMQ_CONTAINER_HOST': 'container_value',
                'RABBITMQ_USER': 'user',
                'RABBITMQ_PASSWORD': 'pass'
            }):
                # Simulate host environment (not container)
                with patch('pewstats_collectors.core.rabbitmq_publisher.Path.exists', return_value=False):
                    pub = RabbitMQPublisher()
                    assert pub.host == 'host_value'

    def test_default_environment_is_prod(self):
        """Test default environment is 'prod' (R compatibility)."""
        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection'):
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'localhost',
                'RABBITMQ_USER': 'user',
                'RABBITMQ_PASSWORD': 'pass'
            }, clear=True):
                pub = RabbitMQPublisher()
                assert pub.environment == 'prod'


# ============================================================================
# Queue/Exchange Naming Tests
# ============================================================================

class TestNamingConventions:
    """Test queue and exchange naming (R compatibility)."""

    def test_build_queue_name(self, publisher):
        """Test queue name format: {type}.{step}.{env}."""
        pub, _ = publisher

        # Test various combinations
        assert pub._build_queue_name("match", "discovered") == "match.discovered.dev"
        assert pub._build_queue_name("telemetry", "processing") == "telemetry.processing.dev"
        assert pub._build_queue_name("dlq", "matches") == "dlq.matches.dev"

    def test_build_queue_name_prod_environment(self):
        """Test queue names in prod environment."""
        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection'):
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'localhost',
                'RABBITMQ_USER': 'user',
                'RABBITMQ_PASSWORD': 'pass',
                'ENVIRONMENT': 'prod'
            }):
                pub = RabbitMQPublisher()
                assert pub._build_queue_name("match", "discovered") == "match.discovered.prod"

    def test_build_exchange_name(self, publisher):
        """Test exchange name format: {type}.exchange.{env}."""
        pub, _ = publisher

        assert pub._build_exchange_name("match") == "match.exchange.dev"
        assert pub._build_exchange_name("telemetry") == "telemetry.exchange.dev"
        assert pub._build_exchange_name("stats") == "stats.exchange.dev"

    def test_build_exchange_name_prod_environment(self):
        """Test exchange names in prod environment."""
        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection'):
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'localhost',
                'RABBITMQ_USER': 'user',
                'RABBITMQ_PASSWORD': 'pass',
                'ENVIRONMENT': 'prod'
            }):
                pub = RabbitMQPublisher()
                assert pub._build_exchange_name("match") == "match.exchange.prod"


# ============================================================================
# Message Publishing Tests
# ============================================================================

class TestMessagePublishing:
    """Test message publishing functionality."""

    def test_publish_message_success(self, publisher):
        """Test successful message publishing."""
        pub, channel = publisher

        message = {
            "match_id": "abc123",
            "timestamp": "2024-01-15 10:30:00"
        }

        result = pub.publish_message("match", "discovered", message)

        assert result is True
        # Verify basic_publish was called
        assert channel.basic_publish.called

    def test_publish_message_adds_metadata(self, publisher):
        """Test that environment and queue_target are added to message."""
        pub, channel = publisher

        message = {"match_id": "abc123"}

        pub.publish_message("match", "discovered", message)

        # Get the actual published payload
        call_args = channel.basic_publish.call_args
        published_body = call_args[1]['body']
        published_data = json.loads(published_body)

        # Verify metadata was added (R compatibility)
        assert published_data["match_id"] == "abc123"
        assert published_data["environment"] == "dev"
        assert published_data["queue_target"] == "match.discovered.dev"

    def test_publish_message_uses_correct_routing_key(self, publisher):
        """Test that routing_key matches queue name."""
        pub, channel = publisher

        pub.publish_message("telemetry", "processing", {"test": "data"})

        call_args = channel.basic_publish.call_args
        routing_key = call_args[1]['routing_key']

        assert routing_key == "telemetry.processing.dev"

    def test_publish_message_uses_default_exchange(self, publisher):
        """Test that default exchange is used (R compatibility)."""
        pub, channel = publisher

        pub.publish_message("match", "discovered", {"test": "data"})

        call_args = channel.basic_publish.call_args
        exchange = call_args[1]['exchange']

        # R uses default exchange (empty string)
        assert exchange == ""

    def test_publish_message_persistence(self, publisher):
        """Test that messages are marked as persistent."""
        pub, channel = publisher

        pub.publish_message("match", "discovered", {"test": "data"})

        call_args = channel.basic_publish.call_args
        properties = call_args[1]['properties']

        # delivery_mode=2 means persistent
        assert properties.delivery_mode == 2

    def test_publish_message_content_type(self, publisher):
        """Test default content type is application/json."""
        pub, channel = publisher

        pub.publish_message("match", "discovered", {"test": "data"})

        call_args = channel.basic_publish.call_args
        properties = call_args[1]['properties']

        assert properties.content_type == "application/json"

    def test_publish_message_custom_properties(self, publisher):
        """Test custom message properties."""
        pub, channel = publisher

        props = {"content_type": "text/plain"}
        pub.publish_message("match", "discovered", {"test": "data"}, properties=props)

        call_args = channel.basic_publish.call_args
        properties = call_args[1]['properties']

        assert properties.content_type == "text/plain"

    def test_publish_message_error_returns_false(self, publisher):
        """Test that errors return False (R compatibility)."""
        pub, channel = publisher

        # Simulate publish error
        channel.basic_publish.side_effect = Exception("Connection lost")

        result = pub.publish_message("match", "discovered", {"test": "data"})

        # Should return False, not raise exception (R behavior)
        assert result is False

    def test_publish_message_different_types_and_steps(self, publisher):
        """Test publishing to various queue types."""
        pub, channel = publisher

        # Test different type/step combinations
        test_cases = [
            ("match", "discovered"),
            ("match", "processing"),
            ("match", "completed"),
            ("match", "failed"),
            ("telemetry", "discovered"),
            ("stats", "processing"),
            ("dlq", "matches")
        ]

        for type_val, step_val in test_cases:
            result = pub.publish_message(type_val, step_val, {"test": "data"})
            assert result is True


# ============================================================================
# Connection Management Tests
# ============================================================================

class TestConnectionManagement:
    """Test connection lifecycle management."""

    def test_lazy_connection_initialization(self):
        """Test that connection is not created until first use."""
        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection') as mock_conn_class:
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'localhost',
                'RABBITMQ_USER': 'user',
                'RABBITMQ_PASSWORD': 'pass'
            }):
                pub = RabbitMQPublisher()

                # Connection should not be created yet
                assert pub._connection is None
                assert not mock_conn_class.called

    def test_connection_created_on_first_publish(self, publisher):
        """Test that connection is created on first publish."""
        pub, channel = publisher

        # Connection is lazy - should be None initially
        pub._connection = None
        pub._channel = None

        # Publish should create connection
        pub.publish_message("match", "discovered", {"test": "data"})

        # Now connection should exist
        assert pub._connection is not None

    def test_connection_reused_for_multiple_publishes(self, publisher):
        """Test that same connection is reused."""
        pub, channel = publisher

        pub.publish_message("match", "discovered", {"msg": "1"})
        pub.publish_message("match", "discovered", {"msg": "2"})
        pub.publish_message("match", "discovered", {"msg": "3"})

        # Should use same connection (not reconnect)
        assert channel.basic_publish.call_count == 3

    def test_context_manager_closes_connection(self):
        """Test that context manager closes connection."""
        mock_conn = Mock()
        mock_channel = Mock()
        mock_conn.is_closed = False
        mock_channel.is_closed = False
        mock_conn.channel.return_value = mock_channel

        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection', return_value=mock_conn):
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'localhost',
                'RABBITMQ_USER': 'user',
                'RABBITMQ_PASSWORD': 'pass'
            }):
                with RabbitMQPublisher() as pub:
                    pub.publish_message("match", "discovered", {"test": "data"})

                # Connection should be closed after exiting context
                mock_channel.close.assert_called_once()
                mock_conn.close.assert_called_once()

    def test_close_method(self, publisher):
        """Test explicit close method."""
        pub, channel = publisher

        # Ensure connection is actually created first
        pub._ensure_connection()

        pub.close()

        channel.close.assert_called_once()
        pub._connection.close.assert_called_once()

    def test_close_safe_to_call_multiple_times(self, publisher):
        """Test that close() can be called multiple times safely."""
        pub, _ = publisher

        pub.close()
        pub.close()
        pub.close()

        # Should not raise exception


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling and logging."""

    def test_connection_failure_raises_error(self):
        """Test that connection failure raises RabbitMQError."""
        # Use AMQPConnectionError instead of generic Exception
        from pika.exceptions import AMQPConnectionError

        with patch('pewstats_collectors.core.rabbitmq_publisher.pika.BlockingConnection', side_effect=AMQPConnectionError("Connection refused")):
            with patch.dict('os.environ', {
                'RABBITMQ_HOST': 'localhost',
                'RABBITMQ_USER': 'user',
                'RABBITMQ_PASSWORD': 'pass'
            }):
                pub = RabbitMQPublisher()

                with pytest.raises(RabbitMQError, match="Failed to connect to RabbitMQ"):
                    pub._ensure_connection()

    def test_publish_failure_logs_warning(self, publisher):
        """Test that publish failures are logged as warnings."""
        pub, channel = publisher

        channel.basic_publish.side_effect = Exception("Channel closed")

        with patch('pewstats_collectors.core.rabbitmq_publisher.logger') as mock_logger:
            result = pub.publish_message("match", "discovered", {"test": "data"})

            assert result is False
            # Verify warning was logged
            assert mock_logger.warning.called
