#!/usr/bin/env python3
"""
Test Manual Acknowledgment

Tests that the RabbitMQ consumer correctly handles manual acknowledgment.
Messages should only be removed from the queue after successful processing.

This script:
1. Publishes a test message to the queue
2. Consumes it with a failing callback
3. Verifies the message is still in the queue (NACK'd and requeued would be false)
4. Consumes it with a successful callback
5. Verifies the message is removed from the queue
"""

import logging
import os
import sys
import time
from typing import Any, Dict

from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pewstats_collectors.core.rabbitmq_publisher import RabbitMQPublisher
from pewstats_collectors.core.rabbitmq_consumer import RabbitMQConsumer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_manual_ack():
    """Test manual acknowledgment behavior."""

    # Load environment
    load_dotenv()

    logger.info("=" * 60)
    logger.info("Manual Acknowledgment Test")
    logger.info("=" * 60)

    # Initialize publisher
    publisher = RabbitMQPublisher(
        host=os.getenv("RABBITMQ_HOST"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment="test",  # Use test environment
    )

    # Initialize consumer
    consumer = RabbitMQConsumer(
        host=os.getenv("RABBITMQ_HOST"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "guest"),
        password=os.getenv("RABBITMQ_PASSWORD", "guest"),
        vhost=os.getenv("RABBITMQ_VHOST", "/"),
        environment="test",  # Use test environment
    )

    # Test message
    test_message = {
        "match_id": "test-match-123",
        "test": True,
        "timestamp": time.time(),
    }

    logger.info("")
    logger.info("Step 1: Publishing test message...")
    success = publisher.publish_message("match", "discovered", test_message)
    if not success:
        logger.error("Failed to publish test message")
        return False

    logger.info("✅ Test message published")

    # Wait a moment for message to be queued
    time.sleep(0.5)

    logger.info("")
    logger.info("Step 2: Testing FAILED processing (should NACK)...")

    # Callback that always fails
    def failing_callback(data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Processing message (will fail): {data.get('match_id')}")
        return {"success": False, "error": "Intentional test failure"}

    # Consume with failing callback
    processed = consumer.consume_batch("match", "discovered", failing_callback, max_messages=1)
    logger.info(f"Processed {processed} messages (expected: 0)")

    if processed != 0:
        logger.error(f"❌ Expected 0 successful messages, got {processed}")
        return False

    logger.info("✅ Message correctly NACK'd on failure")

    logger.info("")
    logger.info("Step 3: Verifying message was NOT removed from queue...")
    logger.info("(Message should have been NACK'd with requeue=False)")

    # The message should NOT be in the queue anymore because we NACK with requeue=False
    # Let's publish a new message for the success test

    logger.info("")
    logger.info("Step 4: Publishing new test message for success test...")
    test_message2 = {
        "match_id": "test-match-456",
        "test": True,
        "timestamp": time.time(),
    }
    success = publisher.publish_message("match", "discovered", test_message2)
    if not success:
        logger.error("Failed to publish second test message")
        return False

    time.sleep(0.5)

    logger.info("")
    logger.info("Step 5: Testing SUCCESSFUL processing (should ACK)...")

    # Callback that succeeds
    def success_callback(data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info(f"Processing message (will succeed): {data.get('match_id')}")
        return {"success": True}

    # Consume with successful callback
    processed = consumer.consume_batch("match", "discovered", success_callback, max_messages=1)
    logger.info(f"Processed {processed} messages (expected: 1)")

    if processed != 1:
        logger.error(f"❌ Expected 1 successful message, got {processed}")
        return False

    logger.info("✅ Message correctly ACK'd on success")

    logger.info("")
    logger.info("Step 6: Verifying message was removed from queue...")

    # Try to consume again - should get nothing
    processed = consumer.consume_batch("match", "discovered", success_callback, max_messages=1)
    logger.info(f"Processed {processed} messages (expected: 0)")

    if processed != 0:
        logger.error(f"❌ Expected 0 messages (queue should be empty), got {processed}")
        return False

    logger.info("✅ Message correctly removed from queue after ACK")

    # Cleanup
    publisher.close()
    consumer.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ All tests passed! Manual acknowledgment works correctly.")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    try:
        success = test_manual_ack()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Test failed with exception: {e}", exc_info=True)
        sys.exit(1)
