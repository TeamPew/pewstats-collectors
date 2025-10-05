"""Unit tests for API Key Manager."""

import pytest
import time
from datetime import datetime, timedelta
from pewstats_collectors.core.api_key_manager import APIKey, APIKeyManager


class TestAPIKey:
    """Test cases for APIKey dataclass."""

    def test_api_key_initialization(self):
        """Test APIKey initializes correctly."""
        key = APIKey(key="test123", rpm_limit=10)
        assert key.key == "test123"
        assert key.rpm_limit == 10
        assert key.request_times == []

    def test_api_key_empty_key_raises_error(self):
        """Test that empty key string raises ValueError."""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            APIKey(key="", rpm_limit=10)

    def test_api_key_invalid_rpm_raises_error(self):
        """Test that invalid RPM limit raises ValueError."""
        with pytest.raises(ValueError, match="RPM limit must be positive"):
            APIKey(key="test123", rpm_limit=0)

        with pytest.raises(ValueError, match="RPM limit must be positive"):
            APIKey(key="test123", rpm_limit=-5)


class TestAPIKeyManager:
    """Test cases for APIKeyManager."""

    def test_initialization_with_valid_keys(self):
        """Test manager initializes with valid keys."""
        keys = [
            {"key": "key1", "rpm": 10},
            {"key": "key2", "rpm": 10},
        ]
        manager = APIKeyManager(keys)
        assert manager._current_index == 0
        assert len(manager._keys) == 2

    def test_initialization_with_empty_keys_raises_error(self):
        """Test that empty keys list raises ValueError."""
        with pytest.raises(ValueError, match="At least one API key is required"):
            APIKeyManager([])

    def test_initialization_with_malformed_keys_raises_error(self):
        """Test that malformed keys raise ValueError."""
        with pytest.raises(ValueError, match="Invalid key config"):
            APIKeyManager([{"key": "key1"}])  # Missing 'rpm'

        with pytest.raises(ValueError, match="Invalid key config"):
            APIKeyManager([{"rpm": 10}])  # Missing 'key'

    def test_select_key_round_robin(self):
        """Test that select_key returns keys in round-robin order."""
        keys = [
            {"key": "key1", "rpm": 10},
            {"key": "key2", "rpm": 10},
            {"key": "key3", "rpm": 10},
        ]
        manager = APIKeyManager(keys)

        # First round
        assert manager.select_key().key == "key1"
        assert manager.select_key().key == "key2"
        assert manager.select_key().key == "key3"

        # Second round (wraps around)
        assert manager.select_key().key == "key1"
        assert manager.select_key().key == "key2"

    def test_can_make_request_when_under_limit(self):
        """Test can_make_request returns True when under limit."""
        keys = [{"key": "key1", "rpm": 10}]
        manager = APIKeyManager(keys)
        key = manager._keys[0]

        # Add 5 recent requests
        for _ in range(5):
            key.request_times.append(datetime.now())

        assert manager.can_make_request(key) is True

    def test_can_make_request_when_at_limit(self):
        """Test can_make_request returns False when at limit."""
        keys = [{"key": "key1", "rpm": 10}]
        manager = APIKeyManager(keys)
        key = manager._keys[0]

        # Add 10 recent requests (at limit)
        for _ in range(10):
            key.request_times.append(datetime.now())

        assert manager.can_make_request(key) is False

    def test_can_make_request_cleans_old_requests(self):
        """Test can_make_request cleans old requests automatically."""
        keys = [{"key": "key1", "rpm": 10}]
        manager = APIKeyManager(keys)
        key = manager._keys[0]

        # Add 10 old requests (> 60 seconds ago)
        old_time = datetime.now() - timedelta(seconds=70)
        for _ in range(10):
            key.request_times.append(old_time)

        # Should clean old requests and return True
        assert manager.can_make_request(key) is True
        assert len(key.request_times) == 0

    def test_record_request(self):
        """Test record_request adds timestamp."""
        keys = [{"key": "key1", "rpm": 10}]
        manager = APIKeyManager(keys)
        key = manager._keys[0]

        before_count = len(key.request_times)
        manager.record_request(key)
        after_count = len(key.request_times)

        assert after_count == before_count + 1
        assert isinstance(key.request_times[-1], datetime)

    def test_wait_if_needed_does_not_wait_when_under_limit(self):
        """Test wait_if_needed returns immediately when under limit."""
        keys = [{"key": "key1", "rpm": 10}]
        manager = APIKeyManager(keys)
        key = manager._keys[0]

        # Add 5 requests
        for _ in range(5):
            key.request_times.append(datetime.now())

        # Should not block
        start = time.time()
        manager.wait_if_needed(key)
        elapsed = time.time() - start

        assert elapsed < 0.1  # Should be nearly instant

    def test_wait_if_needed_waits_when_at_limit(self):
        """Test wait_if_needed blocks when at rate limit."""
        keys = [{"key": "key1", "rpm": 10}]
        manager = APIKeyManager(keys)
        key = manager._keys[0]

        # Add 10 requests at limit, with oldest being 58 seconds ago
        # This means we need to wait ~2 seconds for it to age out
        now = datetime.now()
        key.request_times.append(now - timedelta(seconds=58))
        for _ in range(9):
            key.request_times.append(now)

        # Should block for ~2 seconds
        start = time.time()
        manager.wait_if_needed(key)
        elapsed = time.time() - start

        # Should wait approximately 2 seconds (allow some tolerance)
        assert 1.5 < elapsed < 2.5

    def test_select_key_skips_limited_keys(self):
        """Test select_key skips keys at rate limit."""
        keys = [
            {"key": "key1", "rpm": 10},
            {"key": "key2", "rpm": 10},
            {"key": "key3", "rpm": 10},
        ]
        manager = APIKeyManager(keys)

        # Max out key1
        for _ in range(10):
            manager._keys[0].request_times.append(datetime.now())

        # Max out key2
        for _ in range(10):
            manager._keys[1].request_times.append(datetime.now())

        # First select should return key3 (only available key)
        selected = manager.select_key()
        assert selected.key == "key3"

    def test_select_key_returns_next_when_all_limited(self):
        """Test select_key returns next key even when all are limited."""
        keys = [
            {"key": "key1", "rpm": 10},
            {"key": "key2", "rpm": 10},
        ]
        manager = APIKeyManager(keys)

        # Max out all keys
        for key in manager._keys:
            for _ in range(10):
                key.request_times.append(datetime.now())

        # Should still return a key (round-robin)
        selected = manager.select_key()
        assert selected.key in ["key1", "key2"]

    def test_clean_old_requests(self):
        """Test _clean_old_requests removes old timestamps."""
        keys = [{"key": "key1", "rpm": 10}]
        manager = APIKeyManager(keys)
        key = manager._keys[0]

        # Add mix of old and recent requests
        old_time = datetime.now() - timedelta(seconds=70)
        recent_time = datetime.now() - timedelta(seconds=30)

        key.request_times = [old_time, old_time, recent_time, recent_time]

        manager._clean_old_requests(key)

        # Should only keep the 2 recent ones
        assert len(key.request_times) == 2
        assert all(req_time == recent_time for req_time in key.request_times)

    def test_get_stats(self):
        """Test get_stats returns correct statistics."""
        keys = [
            {"key": "key1", "rpm": 10},
            {"key": "key2", "rpm": 100},
        ]
        manager = APIKeyManager(keys)

        # Add 5 requests to key1
        for _ in range(5):
            manager._keys[0].request_times.append(datetime.now())

        # Add 50 requests to key2
        for _ in range(50):
            manager._keys[1].request_times.append(datetime.now())

        stats = manager.get_stats()

        assert stats["total_keys"] == 2
        assert len(stats["keys"]) == 2

        # Check key1 stats
        key1_stats = stats["keys"][0]
        assert key1_stats["rpm_limit"] == 10
        assert key1_stats["current_requests"] == 5
        assert key1_stats["available_requests"] == 5
        assert key1_stats["utilization_pct"] == 50.0

        # Check key2 stats
        key2_stats = stats["keys"][1]
        assert key2_stats["rpm_limit"] == 100
        assert key2_stats["current_requests"] == 50
        assert key2_stats["available_requests"] == 50
        assert key2_stats["utilization_pct"] == 50.0

    def test_reset_all(self):
        """Test reset_all clears all request histories."""
        keys = [
            {"key": "key1", "rpm": 10},
            {"key": "key2", "rpm": 10},
        ]
        manager = APIKeyManager(keys)

        # Add requests to all keys
        for key in manager._keys:
            for _ in range(5):
                key.request_times.append(datetime.now())

        # Reset
        manager.reset_all()

        # All should be empty
        for key in manager._keys:
            assert len(key.request_times) == 0

    def test_multiple_keys_different_rpm_limits(self):
        """Test manager handles keys with different RPM limits."""
        keys = [
            {"key": "slow_key", "rpm": 10},
            {"key": "fast_key", "rpm": 100},
        ]
        manager = APIKeyManager(keys)

        assert manager._keys[0].rpm_limit == 10
        assert manager._keys[1].rpm_limit == 100

        # Add 50 requests to both
        for key in manager._keys:
            for _ in range(50):
                key.request_times.append(datetime.now())

        # Slow key should be over limit
        assert manager.can_make_request(manager._keys[0]) is False

        # Fast key should still be under limit
        assert manager.can_make_request(manager._keys[1]) is True

    def test_realistic_usage_pattern(self):
        """Test realistic usage pattern with select, wait, and record."""
        keys = [
            {"key": "key1", "rpm": 10},
            {"key": "key2", "rpm": 10},
        ]
        manager = APIKeyManager(keys)

        # Simulate making requests
        for i in range(15):
            key = manager.select_key()
            manager.wait_if_needed(key)  # Should not block until we hit limits
            manager.record_request(key)

        # Should have distributed across both keys
        total_requests = sum(len(key.request_times) for key in manager._keys)
        assert total_requests == 15

        # Both keys should have some requests
        assert len(manager._keys[0].request_times) > 0
        assert len(manager._keys[1].request_times) > 0
