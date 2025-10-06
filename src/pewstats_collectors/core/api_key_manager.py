"""API Key Manager - Round-robin selection with per-key rate limiting.

This module provides API key management for the PUBG API, including:
- Round-robin selection across multiple keys
- Per-key rate limit tracking (RPM - requests per minute)
- Automatic waiting when rate limits are approached
- Exponential backoff on rate limit errors
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List
import logging


logger = logging.getLogger(__name__)


@dataclass
class APIKey:
    """Represents a single API key with rate limiting state.

    Attributes:
        key: The API key string
        rpm_limit: Requests per minute limit for this key
        request_times: List of timestamps for requests in the last 60 seconds
    """

    key: str
    rpm_limit: int
    request_times: List[datetime] = field(default_factory=list)

    def __post_init__(self):
        """Validate API key configuration."""
        if not self.key:
            raise ValueError("API key cannot be empty")
        if self.rpm_limit <= 0:
            raise ValueError(f"RPM limit must be positive, got {self.rpm_limit}")


class APIKeyManager:
    """Manages a pool of API keys with round-robin selection and rate limiting.

    This class handles multiple PUBG API keys, automatically selecting them in
    round-robin fashion and enforcing per-key rate limits to avoid hitting the
    API's rate limit restrictions.

    Example:
        >>> keys = [
        ...     {"key": "abc123", "rpm": 10},
        ...     {"key": "def456", "rpm": 10},
        ... ]
        >>> manager = APIKeyManager(keys)
        >>> key = manager.select_key()
        >>> manager.wait_if_needed(key)
        >>> # Make API request...
        >>> manager.record_request(key)
    """

    def __init__(self, keys: List[Dict[str, any]]):
        """Initialize the API key manager.

        Args:
            keys: List of dicts with 'key' and 'rpm' fields
                  Example: [{"key": "abc123", "rpm": 10}, ...]

        Raises:
            ValueError: If keys list is empty or malformed
        """
        if not keys:
            raise ValueError("At least one API key is required")

        self._keys: List[APIKey] = []
        for key_config in keys:
            if "key" not in key_config or "rpm" not in key_config:
                raise ValueError(
                    f"Invalid key config: {key_config}. Must have 'key' and 'rpm' fields"
                )

            api_key = APIKey(key=key_config["key"], rpm_limit=key_config["rpm"])
            self._keys.append(api_key)

        self._current_index = 0
        logger.info(f"Initialized APIKeyManager with {len(self._keys)} keys")

    def select_key(self) -> APIKey:
        """Select the next available API key using round-robin with proactive pacing.

        Strategy:
        - Try all keys in round-robin order to find one under the limit
        - If all keys are at limit, wait for the soonest available slot
        - Proactively wait BEFORE making a request to avoid hitting the limit
        - Each key limited to N requests per 60 seconds (e.g., 10 RPM)

        Returns:
            The selected API key (ready to use immediately)
        """
        # First pass: try to find a key that's immediately available
        for _ in range(len(self._keys)):
            key = self._keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._keys)

            # Clean old requests (older than 60 seconds)
            self._clean_old_requests(key)

            # If under limit, return this key immediately
            if len(key.request_times) < key.rpm_limit:
                return key

        # All keys are at limit - find which one will be ready soonest
        min_wait_time = float("inf")
        next_available_key = self._keys[0]

        for key in self._keys:
            self._clean_old_requests(key)
            if len(key.request_times) >= key.rpm_limit:
                oldest_request = min(key.request_times)
                time_since_oldest = datetime.now() - oldest_request
                wait_time = (timedelta(seconds=60) - time_since_oldest).total_seconds()

                if wait_time < min_wait_time:
                    min_wait_time = wait_time
                    next_available_key = key

        # Wait for the soonest slot to free up
        if min_wait_time > 0:
            logger.info(
                f"All keys at limit. Waiting {min_wait_time:.2f}s for next slot"
            )
            time.sleep(min_wait_time)
            self._clean_old_requests(next_available_key)

        return next_available_key

    def can_make_request(self, key: APIKey) -> bool:
        """Check if a request can be made with this key without hitting rate limit.

        Args:
            key: The API key to check

        Returns:
            True if a request can be made immediately, False otherwise
        """
        self._clean_old_requests(key)
        return len(key.request_times) < key.rpm_limit

    def wait_if_needed(self, key: APIKey) -> None:
        """Wait if necessary to avoid exceeding rate limit for this key.

        This method will block until it's safe to make a request with the given key.
        It calculates the time needed to wait based on the oldest request in the
        current window.

        Args:
            key: The API key to check
        """
        self._clean_old_requests(key)

        if len(key.request_times) < key.rpm_limit:
            # Under rate limit, no need to wait
            return

        # At rate limit, need to wait for oldest request to age out
        oldest_request = min(key.request_times)
        time_since_oldest = datetime.now() - oldest_request
        wait_time = timedelta(seconds=60) - time_since_oldest

        if wait_time.total_seconds() > 0:
            wait_seconds = wait_time.total_seconds()
            logger.info(
                f"Rate limit reached ({len(key.request_times)}/{key.rpm_limit} RPM). "
                f"Waiting {wait_seconds:.2f} seconds"
            )
            time.sleep(wait_seconds)

            # Clean again after waiting
            self._clean_old_requests(key)

    def record_request(self, key: APIKey) -> None:
        """Record that a request was made with this key.

        This updates the key's request history with the current timestamp.
        Old requests (> 60 seconds) are automatically cleaned up.

        Args:
            key: The API key that was used
        """
        key.request_times.append(datetime.now())
        self._clean_old_requests(key)

        logger.debug(
            f"Recorded request. Current count: {len(key.request_times)}/{key.rpm_limit} RPM"
        )

    def _clean_old_requests(self, key: APIKey) -> None:
        """Remove request timestamps older than 60 seconds.

        This keeps the request_times list clean and prevents unbounded growth.

        Args:
            key: The API key to clean
        """
        cutoff_time = datetime.now() - timedelta(seconds=60)
        key.request_times = [req_time for req_time in key.request_times if req_time > cutoff_time]

    def get_stats(self) -> Dict[str, any]:
        """Get statistics about API key usage.

        Returns:
            Dict with statistics including per-key request counts
        """
        stats = {"total_keys": len(self._keys), "keys": []}

        for i, key in enumerate(self._keys):
            self._clean_old_requests(key)
            key_stats = {
                "index": i,
                "rpm_limit": key.rpm_limit,
                "current_requests": len(key.request_times),
                "available_requests": key.rpm_limit - len(key.request_times),
                "utilization_pct": (len(key.request_times) / key.rpm_limit) * 100,
            }
            stats["keys"].append(key_stats)

        return stats

    def reset_all(self) -> None:
        """Reset request history for all keys.

        This is primarily useful for testing. In production, request times
        naturally age out after 60 seconds.
        """
        for key in self._keys:
            key.request_times.clear()
        logger.info("Reset all API key request histories")
