"""Unit tests for RabbitMQConsumer.

Tests AMQP-based consumption with mocked pika connections.
Ensures R BaseWorker parity.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock, call

from pewstats_collectors.core.rabbitmq_consumer import RabbitMQConsumer, RabbitMQConsumerError


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
def consumer(mock_connection):
    """Create RabbitMQConsumer with mocked connection."""
    conn, channel = mock_connection

    with patch('pewstats_collectors.core.rabbitmq_consumer.pika.BlockingConnection', return_value=conn):
        consumer = RabbitMQConsumer(
            host='localhost',
            username='test',
            password='pass',
            environment='dev'
        )
        yield consumer, channel


# ============================================================================
# Initialization Tests
# ============================================================================

class TestRabbitMQConsumerInitialization:
    """Test consumer initialization."""

    def test_initialization_with_defaults(self):
        """Test initialization with default parameters."""
        with patch('pewstats_collectors.core.rabbitmq_consumer.pika.BlockingConnection'):
            consumer = RabbitMQConsumer(
                host='localhost',
                username='user',
                password='pass'
            )

            assert consumer.host == 'localhost'
            assert consumer.port == 5672
            assert consumer.environment == 'prod'  # Default
            assert consumer.prefetch_count == 1

    def test_initialization_with_custom_params(self):
        """Test initialization with custom parameters."""
        with patch('pewstats_collectors.core.rabbitmq_consumer.pika.BlockingConnection'):
            consumer = RabbitMQConsumer(
                host='rabbitmq.example.com',
                port=5673,
                username='custom_user',
                password='custom_pass',
                vhost='/custom',
                environment='staging',
                prefetch_count=10
            )

            assert consumer.host == 'rabbitmq.example.com'
            assert consumer.port == 5673
            assert consumer.vhost == '/custom'
            assert consumer.environment == 'staging'
            assert consumer.prefetch_count == 10


# ============================================================================
# Queue Naming Tests
# ============================================================================

class TestQueueNaming:
    """Test queue naming (R compatibility)."""

    def test_build_queue_name(self, consumer):
        """Test queue name format: {type}.{step}.{env}."""
        cons, _ = consumer

        assert cons._build_queue_name("match", "discovered") == "match.discovered.dev"
        assert cons._build_queue_name("telemetry", "processing") == "telemetry.processing.dev"
        assert cons._build_queue_name("dlq", "matches") == "dlq.matches.dev"

    def test_build_queue_name_prod_environment(self):
        """Test queue names in prod environment."""
        with patch('pewstats_collectors.core.rabbitmq_consumer.pika.BlockingConnection'):
            consumer = RabbitMQConsumer(
                host='localhost',
                username='user',
                password='pass',
                environment='prod'
            )

            assert consumer._build_queue_name("match", "discovered") == "match.discovered.prod"


# ============================================================================
# Message Processing Tests
# ============================================================================

class TestMessageProcessing:
    """Test message processing logic."""

    def test_process_message_success(self, consumer):
        """Test successful message processing."""
        cons, _ = consumer

        message_data = {"match_id": "abc123", "timestamp": "2024-01-15"}
        message_body = json.dumps(message_data).encode('utf-8')

        def callback(data):
            assert data["match_id"] == "abc123"
            return {"success": True}

        result = cons._process_message(message_body, callback)

        assert result["success"] is True

    def test_process_message_failure(self, consumer):
        """Test failed message processing."""
        cons, _ = consumer

        message_data = {"match_id": "abc123"}
        message_body = json.dumps(message_data).encode('utf-8')

        def callback(data):
            return {"success": False, "error": "Processing failed"}

        result = cons._process_message(message_body, callback)

        assert result["success"] is False
        assert result["error"] == "Processing failed"

    def test_process_message_exception_in_callback(self, consumer):
        """Test exception handling in callback."""
        cons, _ = consumer

        message_data = {"match_id": "abc123"}
        message_body = json.dumps(message_data).encode('utf-8')

        def callback(data):
            raise Exception("Callback error")

        result = cons._process_message(message_body, callback)

        assert result["success"] is False
        assert "Exception during message processing" in result["error"]

    def test_process_message_invalid_json(self, consumer):
        """Test handling of invalid JSON."""
        cons, _ = consumer

        invalid_json = b"not valid json"

        def callback(data):
            return {"success": True}

        result = cons._process_message(invalid_json, callback)

        assert result["success"] is False
        assert "Failed to parse message JSON" in result["error"]

    def test_process_message_invalid_callback_return(self, consumer):
        """Test handling of invalid callback return format."""
        cons, _ = consumer

        message_data = {"match_id": "abc123"}
        message_body = json.dumps(message_data).encode('utf-8')

        def callback(data):
            return "invalid"  # Should return dict

        result = cons._process_message(message_body, callback)

        assert result["success"] is False
        assert "Invalid callback return format" in result["error"]


# ============================================================================
# Batch Consumption Tests
# ============================================================================

class TestBatchConsumption:
    """Test batch consumption (R processQueueMessages equivalent)."""

    def test_consume_batch_success(self, consumer):
        """Test successful batch consumption."""
        cons, channel = consumer

        # Mock messages
        messages = [
            (Mock(delivery_tag=1), Mock(), json.dumps({"match_id": "m1"}).encode()),
            (Mock(delivery_tag=2), Mock(), json.dumps({"match_id": "m2"}).encode()),
            (Mock(delivery_tag=3), Mock(), json.dumps({"match_id": "m3"}).encode()),
        ]

        # Add timeout to end iteration
        messages.append((None, None, None))

        channel.consume.return_value = iter(messages)

        def callback(data):
            return {"success": True}

        cons._ensure_connection()
        result = cons.consume_batch("match", "discovered", callback, max_messages=10)

        assert result == 3  # All 3 messages processed

    def test_consume_batch_with_failures(self, consumer):
        """Test batch consumption with some failures."""
        cons, channel = consumer

        messages = [
            (Mock(delivery_tag=1), Mock(), json.dumps({"match_id": "m1"}).encode()),
            (Mock(delivery_tag=2), Mock(), json.dumps({"match_id": "m2"}).encode()),
        ]
        messages.append((None, None, None))

        channel.consume.return_value = iter(messages)

        call_count = [0]

        def callback(data):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"success": True}
            else:
                return {"success": False, "error": "Failed"}

        cons._ensure_connection()
        result = cons.consume_batch("match", "discovered", callback, max_messages=10)

        assert result == 1  # Only first message succeeded

    def test_consume_batch_respects_max_messages(self, consumer):
        """Test that batch consumption respects max_messages limit."""
        cons, channel = consumer

        # Create 10 messages
        messages = [(Mock(delivery_tag=i), Mock(), json.dumps({"match_id": f"m{i}"}).encode()) for i in range(10)]
        messages.append((None, None, None))

        channel.consume.return_value = iter(messages)

        def callback(data):
            return {"success": True}

        cons._ensure_connection()
        result = cons.consume_batch("match", "discovered", callback, max_messages=5)

        # Should stop at 5 messages
        assert result == 5


# ============================================================================
# Connection Management Tests
# ============================================================================

class TestConnectionManagement:
    """Test connection lifecycle management."""

    def test_lazy_connection_initialization(self):
        """Test that connection is not created until first use."""
        with patch('pewstats_collectors.core.rabbitmq_consumer.pika.BlockingConnection') as mock_conn_class:
            consumer = RabbitMQConsumer(
                host='localhost',
                username='user',
                password='pass'
            )

            # Connection should not be created yet
            assert consumer._connection is None
            assert not mock_conn_class.called

    def test_ensure_connection_creates_connection(self, consumer):
        """Test that _ensure_connection creates connection."""
        cons, channel = consumer

        # Reset connection
        cons._connection = None
        cons._channel = None

        cons._ensure_connection()

        assert cons._connection is not None
        assert cons._channel is not None

    def test_ensure_connection_sets_prefetch(self, consumer):
        """Test that prefetch QoS is set."""
        cons, channel = consumer

        cons._ensure_connection()

        # Verify basic_qos was called with prefetch_count
        channel.basic_qos.assert_called_with(prefetch_count=1)

    def test_close_method(self, consumer):
        """Test explicit close method."""
        cons, channel = consumer

        cons._ensure_connection()
        cons.close()

        channel.close.assert_called_once()
        cons._connection.close.assert_called_once()

    def test_close_safe_to_call_multiple_times(self, consumer):
        """Test that close() can be called multiple times safely."""
        cons, _ = consumer

        cons.close()
        cons.close()
        cons.close()

        # Should not raise exception

    def test_context_manager(self, consumer):
        """Test context manager support."""
        cons, channel = consumer

        with cons as c:
            assert c is not None

        # Connection should be closed
        channel.close.assert_called()
        cons._connection.close.assert_called()


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling and logging."""

    def test_connection_failure_raises_error(self):
        """Test that connection failure raises RabbitMQConsumerError."""
        from pika.exceptions import AMQPConnectionError

        with patch('pewstats_collectors.core.rabbitmq_consumer.pika.BlockingConnection', side_effect=AMQPConnectionError("Connection refused")):
            consumer = RabbitMQConsumer(
                host='localhost',
                username='user',
                password='pass'
            )

            with pytest.raises(RabbitMQConsumerError, match="Failed to connect to RabbitMQ"):
                consumer._ensure_connection()

    def test_stop_consuming_when_not_consuming(self, consumer):
        """Test stop_consuming when not actually consuming."""
        cons, _ = consumer

        # Should not raise exception
        cons.stop_consuming()


# ============================================================================
# Stats Tests
# ============================================================================

class TestStatistics:
    """Test statistics tracking."""

    def test_get_processed_count(self, consumer):
        """Test tracking of processed message count."""
        cons, _ = consumer

        assert cons.get_processed_count() == 0

        # Simulate processing messages
        message_data = {"match_id": "abc123"}
        message_body = json.dumps(message_data).encode('utf-8')

        def callback(data):
            return {"success": True}

        cons._process_message(message_body, callback)

        # Processed count should still be 0 (only _on_message_callback increments it)
        assert cons.get_processed_count() == 0

    def test_processed_count_increments(self, consumer):
        """Test that processed count increments correctly."""
        cons, channel = consumer

        # Directly increment processed count
        cons._processed_count = 5

        assert cons.get_processed_count() == 5
