"""PUBG API Client - HTTP wrapper for PUBG API with rate limiting and retries.

This module provides a client for interacting with the PUBG API, including:
- Automatic API key selection and rotation via APIKeyManager
- Rate limiting enforcement
- Retry logic with exponential backoff
- Response caching (5-minute TTL)
- Automatic chunking for >10 players
- Match discovery and metadata extraction
- Database integration for duplicate detection
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Callable
import requests
from requests.exceptions import RequestException, HTTPError, Timeout

from pewstats_collectors.core.api_key_manager import APIKeyManager


logger = logging.getLogger(__name__)


class PUBGAPIError(Exception):
    """Base exception for PUBG API errors."""
    pass


class RateLimitError(PUBGAPIError):
    """Raised when rate limit is exceeded."""
    pass


class NotFoundError(PUBGAPIError):
    """Raised when resource is not found (404)."""
    pass


class PUBGClient:
    """Client for PUBG API with rate limiting, caching, and business logic.

    This client handles all HTTP communication with the PUBG API, including:
    - Automatic API key management and rotation
    - Rate limit enforcement and retry logic
    - Response caching with TTL
    - Automatic chunking for player batches
    - Match discovery and metadata extraction
    - Integration with database for duplicate detection

    Example:
        >>> keys = [{"key": "abc123", "rpm": 10}]
        >>> key_manager = APIKeyManager(keys)
        >>> client = PUBGClient(key_manager, get_existing_match_ids_func, platform="steam")
        >>> new_matches = client.get_new_matches(["player1", "player2"])
    """

    BASE_URL = "https://api.pubg.com/shards"
    CONTENT_TYPE = "application/vnd.api+json"
    CACHE_TTL_SECONDS = 300  # 5 minutes

    # Map name translations (from R code)
    MAP_TRANSLATIONS = {
        "Baltic_Main": "Erangel (Remastered)",
        "Chimera_Main": "Paramo",
        "Desert_Main": "Miramar",
        "DihorOtok_Main": "Vikendi",
        "Erangel_Main": "Erangel",
        "Heaven_Main": "Haven",
        "Kiki_Main": "Deston",
        "Range_Main": "Camp Jackal",
        "Savage_Main": "Sanhok",
        "Summerland_Main": "Karakin",
        "Tiger_Main": "Taego",
        "Neon_Main": "Rondo"
    }

    def __init__(
        self,
        api_key_manager: APIKeyManager,
        get_existing_match_ids: Callable[[], Set[str]],
        platform: str = "steam",
        max_retries: int = 3,
        timeout: int = 30
    ):
        """Initialize PUBG API client.

        Args:
            api_key_manager: APIKeyManager instance for key selection
            get_existing_match_ids: Callable that returns set of existing match IDs from DB
            platform: Gaming platform (default: "steam")
            max_retries: Maximum number of retry attempts (default: 3)
            timeout: Request timeout in seconds (default: 30)
        """
        self.key_manager = api_key_manager
        self.get_existing_match_ids = get_existing_match_ids
        self.platform = platform
        self.max_retries = max_retries
        self.timeout = timeout

        # Cache storage: {cache_key: {"data": response, "time": datetime}}
        self._cache: Dict[str, Dict[str, Any]] = {}

        logger.info(f"Initialized PUBGClient for platform '{platform}'")

    def get_player_info(self, player_names: List[str]) -> Dict[str, Any]:
        """Get player information for one or more players.

        Automatically chunks requests if >10 players provided.
        Caches responses for 5 minutes.

        Args:
            player_names: List of player names (auto-chunks if >10)

        Returns:
            Parsed JSON response from PUBG API with combined data if chunked

        Raises:
            ValueError: If player_names is empty
            PUBGAPIError: If API request fails
        """
        if not player_names:
            raise ValueError("player_names cannot be empty")

        # Check cache first
        cache_key = f"players_{','.join(sorted(player_names))}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {len(player_names)} player(s)")
            return cached

        # Split into chunks of 10 if needed
        chunks = [player_names[i:i+10] for i in range(0, len(player_names), 10)]

        if len(chunks) == 1:
            # Single request
            params = {"filter[playerNames]": ",".join(player_names)}
            logger.debug(f"Fetching player info for {len(player_names)} player(s)")
            result = self._make_request("/players", params=params)
        else:
            # Multiple requests - combine results
            logger.debug(f"Fetching player info for {len(player_names)} players in {len(chunks)} chunks")
            all_players = None

            for chunk in chunks:
                params = {"filter[playerNames]": ",".join(chunk)}
                response = self._make_request("/players", params=params)

                if all_players is None:
                    all_players = response
                else:
                    # Combine data from multiple chunks
                    if "data" in response:
                        all_players["data"].extend(response["data"])

            result = all_players

        # Cache the result
        self._set_cached(cache_key, result)
        return result

    def get_new_matches(self, player_names: List[str]) -> List[str]:
        """Discover new match IDs for players by comparing with existing matches.

        This is the core match discovery logic from the R implementation.
        It fetches player data, extracts match IDs, and filters out matches
        that already exist in the database.

        Args:
            player_names: List of player names to check for new matches

        Returns:
            List of new match IDs not yet in database

        Raises:
            ValueError: If player_names is empty
        """
        if not player_names:
            raise ValueError("player_names cannot be empty")

        logger.info(f"Getting new matches for {len(player_names)} player(s): {', '.join(player_names)}")

        # Get existing matches from database
        existing_match_ids = self.get_existing_match_ids()
        logger.info(f"Found {len(existing_match_ids)} existing matches in database")

        # Get player data (auto-chunks if needed)
        player_data = self.get_player_info(player_names)

        if not player_data or "data" not in player_data:
            logger.warning("No player data returned from API")
            return []

        # Extract match IDs from player data
        all_match_ids = set()
        for player in player_data["data"]:
            player_name = player.get("attributes", {}).get("name", "Unknown")
            matches = player.get("relationships", {}).get("matches", {}).get("data", [])

            logger.debug(f"Player '{player_name}' has {len(matches)} total matches")

            for match in matches:
                match_id = match.get("id")
                if match_id:
                    all_match_ids.add(match_id)

        # Filter out existing matches
        new_match_ids = all_match_ids - existing_match_ids
        logger.info(f"Found {len(new_match_ids)} new matches (total {len(all_match_ids)}, existing {len(existing_match_ids)})")

        return list(new_match_ids)

    def get_match(self, match_id: str) -> Dict[str, Any]:
        """Get detailed match data for a specific match.

        Caches responses for 5 minutes.

        Args:
            match_id: Match UUID

        Returns:
            Parsed JSON response from PUBG API

        Raises:
            ValueError: If match_id is empty
            NotFoundError: If match not found
            PUBGAPIError: If API request fails
        """
        if not match_id:
            raise ValueError("match_id cannot be empty")

        # Check cache first
        cache_key = f"match_{match_id}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for match {match_id}")
            return cached

        logger.debug(f"Fetching match data for {match_id}")
        result = self._make_request(f"/matches/{match_id}")

        # Cache the result
        self._set_cached(cache_key, result)
        return result

    def extract_match_metadata(self, match_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key metadata from match data response.

        This replicates the extractMatchMetadata logic from R code.

        Args:
            match_data: Raw match data from get_match()

        Returns:
            Dict with match_id, map_name, match_datetime, game_mode, game_type, telemetry_url

        Raises:
            ValueError: If match_data is invalid
        """
        if not match_data or "data" not in match_data or not match_data["data"]:
            raise ValueError("Invalid match data provided")

        data = match_data["data"]
        attributes = data.get("attributes", {})

        # Extract basic metadata
        metadata = {
            "match_id": data.get("id"),
            "map_name": self.transform_map_name(attributes.get("mapName", "")),
            "match_datetime": self._parse_datetime(attributes.get("createdAt")),
            "game_mode": attributes.get("gameMode"),
            "game_type": attributes.get("matchType", "unknown")
        }

        # Extract telemetry URL
        try:
            # Get asset ID from relationships
            assets = data.get("relationships", {}).get("assets", {}).get("data", [])
            if not assets:
                logger.warning(f"No assets found for match {metadata['match_id']}")
                metadata["telemetry_url"] = None
                return metadata

            asset_id = assets[0].get("id")

            # Find asset in included section
            included = match_data.get("included", [])
            telemetry_asset = None
            for item in included:
                if item.get("type") == "asset" and item.get("id") == asset_id:
                    telemetry_asset = item
                    break

            if telemetry_asset:
                metadata["telemetry_url"] = telemetry_asset.get("attributes", {}).get("URL")
            else:
                logger.warning(f"Telemetry asset not found in included section for match {metadata['match_id']}")
                metadata["telemetry_url"] = None

        except Exception as e:
            logger.error(f"Failed to extract telemetry URL: {e}")
            metadata["telemetry_url"] = None

        return metadata

    def transform_map_name(self, internal_name: str) -> str:
        """Transform internal PUBG map name to display name.

        Args:
            internal_name: Internal map name (e.g., "Baltic_Main")

        Returns:
            Display name (e.g., "Erangel (Remastered)") or original if not found
        """
        if not internal_name:
            return internal_name

        return self.MAP_TRANSLATIONS.get(internal_name, internal_name)

    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO 8601 datetime string from PUBG API.

        Args:
            datetime_str: ISO 8601 datetime string

        Returns:
            Parsed datetime object or None if invalid
        """
        if not datetime_str:
            return None

        try:
            # PUBG API format: "2024-01-01T12:00:00Z"
            return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        except Exception as e:
            logger.warning(f"Failed to parse datetime '{datetime_str}': {e}")
            return None

    def _get_cached(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if still valid.

        Args:
            cache_key: Cache key

        Returns:
            Cached data if valid, None otherwise
        """
        if cache_key not in self._cache:
            return None

        cached_item = self._cache[cache_key]
        cache_time = cached_item["time"]
        age = datetime.now() - cache_time

        if age.total_seconds() < self.CACHE_TTL_SECONDS:
            return cached_item["data"]

        # Expired - remove from cache
        del self._cache[cache_key]
        return None

    def _set_cached(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Store response in cache.

        Args:
            cache_key: Cache key
            data: Response data to cache
        """
        self._cache[cache_key] = {
            "data": data,
            "time": datetime.now()
        }

    def clear_cache(self) -> None:
        """Clear all cached responses.

        Useful for testing or forcing fresh data.
        """
        self._cache.clear()
        logger.debug("Cache cleared")

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, str]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """Make an HTTP request to PUBG API with retries.

        Args:
            endpoint: API endpoint (e.g., "/players")
            params: Query parameters
            retry_count: Current retry attempt (for internal use)

        Returns:
            Parsed JSON response

        Raises:
            PUBGAPIError: If request fails after all retries
        """
        # Select API key and wait if needed
        api_key = self.key_manager.select_key()
        self.key_manager.wait_if_needed(api_key)

        # Build full URL
        url = f"{self.BASE_URL}/{self.platform}{endpoint}"

        # Build headers
        headers = {
            "Authorization": f"Bearer {api_key.key}",
            "Accept": self.CONTENT_TYPE
        }

        try:
            # Make request
            logger.debug(f"Making request to {endpoint}")
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=self.timeout
            )

            # Record successful request
            self.key_manager.record_request(api_key)

            # Handle HTTP errors
            if response.status_code == 404:
                raise NotFoundError(f"Resource not found: {endpoint}")

            if response.status_code == 429:
                # Rate limit hit - handle with retry
                logger.warning(f"Rate limit hit (429) on {endpoint}")
                return self._handle_rate_limit_retry(endpoint, params, retry_count)

            # Raise for other HTTP errors
            response.raise_for_status()

            # Parse and return JSON
            data = response.json()

            # Check for API errors in response
            if "errors" in data:
                error_detail = data["errors"][0].get("detail", "Unknown error")
                raise PUBGAPIError(f"API error: {error_detail}")

            return data

        except Timeout as e:
            logger.error(f"Timeout on {endpoint}: {e}")
            return self._handle_retry(endpoint, params, retry_count, e)

        except HTTPError as e:
            logger.error(f"HTTP error on {endpoint}: {e}")
            if retry_count < self.max_retries:
                return self._handle_retry(endpoint, params, retry_count, e)
            raise PUBGAPIError(f"HTTP error: {e}") from e

        except RequestException as e:
            logger.error(f"Request error on {endpoint}: {e}")
            return self._handle_retry(endpoint, params, retry_count, e)

        except ValueError as e:
            # JSON parsing error
            logger.error(f"Invalid JSON response from {endpoint}: {e}")
            raise PUBGAPIError(f"Invalid JSON response: {e}") from e

    def _handle_rate_limit_retry(
        self,
        endpoint: str,
        params: Optional[Dict[str, str]],
        retry_count: int
    ) -> Dict[str, Any]:
        """Handle rate limit (429) response with exponential backoff.

        Args:
            endpoint: API endpoint
            params: Query parameters
            retry_count: Current retry attempt

        Returns:
            Parsed JSON response from retry

        Raises:
            RateLimitError: If max retries exceeded
        """
        if retry_count >= self.max_retries:
            raise RateLimitError(f"Rate limit exceeded after {self.max_retries} retries")

        # Exponential backoff: 2^retry seconds
        wait_time = 2 ** retry_count
        logger.info(f"Rate limit hit, waiting {wait_time}s before retry {retry_count + 1}")
        time.sleep(wait_time)

        return self._make_request(endpoint, params, retry_count + 1)

    def _handle_retry(
        self,
        endpoint: str,
        params: Optional[Dict[str, str]],
        retry_count: int,
        error: Exception
    ) -> Dict[str, Any]:
        """Handle request retry with exponential backoff.

        Args:
            endpoint: API endpoint
            params: Query parameters
            retry_count: Current retry attempt
            error: Exception that triggered retry

        Returns:
            Parsed JSON response from retry

        Raises:
            PUBGAPIError: If max retries exceeded
        """
        if retry_count >= self.max_retries:
            raise PUBGAPIError(f"Request failed after {self.max_retries} retries: {error}") from error

        # Exponential backoff: 2^retry seconds
        wait_time = 2 ** retry_count
        logger.info(f"Retrying {endpoint} in {wait_time}s (attempt {retry_count + 1}/{self.max_retries})")
        time.sleep(wait_time)

        return self._make_request(endpoint, params, retry_count + 1)

    def health_check(self) -> bool:
        """Perform a health check by making a simple API request.

        This attempts to fetch a single player to verify API connectivity.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Try to get a player (this will likely 404, but that's ok for health check)
            # We just want to verify we can reach the API
            self._make_request("/players", params={"filter[playerNames]": "healthcheck"})
            return True
        except NotFoundError:
            # 404 is actually a successful response for health check
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
