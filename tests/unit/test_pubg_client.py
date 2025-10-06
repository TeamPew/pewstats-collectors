"""Unit tests for PUBG Client with full business logic coverage."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from requests.exceptions import Timeout

from pewstats_collectors.core.api_key_manager import APIKeyManager
from pewstats_collectors.core.pubg_client import PUBGClient, RateLimitError, NotFoundError


@pytest.fixture
def mock_key_manager():
    """Create a mock APIKeyManager."""
    keys = [{"key": "test_key_123", "rpm": 10}]
    return APIKeyManager(keys)


@pytest.fixture
def mock_get_existing_match_ids():
    """Create a mock function that returns existing match IDs."""

    def _get_existing():
        return {"existing-match-1", "existing-match-2"}

    return _get_existing


@pytest.fixture
def pubg_client(mock_key_manager, mock_get_existing_match_ids):
    """Create a PUBGClient instance with mocks."""
    return PUBGClient(mock_key_manager, mock_get_existing_match_ids, platform="steam")


class TestPUBGClientInitialization:
    """Test cases for PUBGClient initialization."""

    def test_initialization_with_defaults(self, mock_key_manager, mock_get_existing_match_ids):
        """Test client initializes with default values."""
        client = PUBGClient(mock_key_manager, mock_get_existing_match_ids)
        assert client.platform == "steam"
        assert client.max_retries == 3
        assert client.timeout == 30
        assert client._cache == {}

    def test_initialization_with_custom_values(self, mock_key_manager, mock_get_existing_match_ids):
        """Test client initializes with custom values."""
        client = PUBGClient(
            mock_key_manager,
            mock_get_existing_match_ids,
            platform="console",
            max_retries=5,
            timeout=60,
        )
        assert client.platform == "console"
        assert client.max_retries == 5
        assert client.timeout == 60


class TestGetPlayerInfo:
    """Test cases for get_player_info method."""

    def test_get_player_info_with_empty_list_raises_error(self, pubg_client):
        """Test that empty player list raises ValueError."""
        with pytest.raises(ValueError, match="player_names cannot be empty"):
            pubg_client.get_player_info([])

    @patch("requests.get")
    def test_get_player_info_single_player(self, mock_get, pubg_client):
        """Test fetching single player."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"type": "player", "attributes": {"name": "player1"}}]
        }
        mock_get.return_value = mock_response

        result = pubg_client.get_player_info(["player1"])

        assert "data" in result
        assert len(result["data"]) == 1

    @patch("requests.get")
    def test_get_player_info_auto_chunks_large_list(self, mock_get, pubg_client):
        """Test that >10 players are automatically chunked."""
        # Create 15 players (should make 2 requests)
        players = [f"player{i}" for i in range(15)]

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"type": "player", "attributes": {"name": "test"}}]
        }
        mock_get.return_value = mock_response

        result = pubg_client.get_player_info(players)

        # Should have made 2 API calls (10 + 5 players)
        assert mock_get.call_count == 2

        # Result should combine both responses
        assert "data" in result
        assert len(result["data"]) == 2  # 2 chunks = 2 player objects

    @patch("requests.get")
    def test_get_player_info_uses_cache(self, mock_get, pubg_client):
        """Test that cached responses are reused."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        # First call
        pubg_client.get_player_info(["player1"])

        # Second call (should use cache)
        result = pubg_client.get_player_info(["player1"])

        # Should only make one API call
        assert mock_get.call_count == 1
        assert "data" in result

    def test_get_player_info_cache_expires(self, pubg_client):
        """Test that cache expires after TTL."""
        # Manually set a cached item with old timestamp
        cache_key = "players_player1"
        old_time = datetime.now() - timedelta(seconds=400)  # Older than 300s TTL
        pubg_client._cache[cache_key] = {"data": {"data": []}, "time": old_time}

        with patch("requests.get") as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": []}
            mock_get.return_value = mock_response

            # Should make new request (cache expired)
            pubg_client.get_player_info(["player1"])

            assert mock_get.call_count == 1


class TestGetNewMatches:
    """Test cases for get_new_matches method."""

    def test_get_new_matches_empty_players_raises_error(self, pubg_client):
        """Test that empty player list raises ValueError."""
        with pytest.raises(ValueError, match="player_names cannot be empty"):
            pubg_client.get_new_matches([])

    @patch("requests.get")
    def test_get_new_matches_filters_existing(self, mock_get, pubg_client):
        """Test that existing matches are filtered out."""
        # Mock API response with mix of new and existing matches
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "attributes": {"name": "player1"},
                    "relationships": {
                        "matches": {
                            "data": [
                                {"id": "existing-match-1"},  # In DB
                                {"id": "existing-match-2"},  # In DB
                                {"id": "new-match-1"},  # New!
                                {"id": "new-match-2"},  # New!
                            ]
                        }
                    },
                }
            ]
        }
        mock_get.return_value = mock_response

        # Mock DB returns 2 existing matches
        pubg_client.get_existing_match_ids = lambda: {"existing-match-1", "existing-match-2"}

        result = pubg_client.get_new_matches(["player1"])

        # Should only return the 2 new matches
        assert len(result) == 2
        assert "new-match-1" in result
        assert "new-match-2" in result
        assert "existing-match-1" not in result

    @patch("requests.get")
    def test_get_new_matches_handles_multiple_players(self, mock_get, pubg_client):
        """Test match discovery across multiple players."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "attributes": {"name": "player1"},
                    "relationships": {"matches": {"data": [{"id": "match-1"}, {"id": "match-2"}]}},
                },
                {
                    "attributes": {"name": "player2"},
                    "relationships": {"matches": {"data": [{"id": "match-2"}, {"id": "match-3"}]}},
                },
            ]
        }
        mock_get.return_value = mock_response

        pubg_client.get_existing_match_ids = lambda: set()

        result = pubg_client.get_new_matches(["player1", "player2"])

        # Should deduplicate match-2 (both players played it)
        assert len(result) == 3
        assert set(result) == {"match-1", "match-2", "match-3"}

    @patch("requests.get")
    def test_get_new_matches_returns_empty_when_no_new(self, mock_get, pubg_client):
        """Test that empty list returned when no new matches."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "attributes": {"name": "player1"},
                    "relationships": {"matches": {"data": [{"id": "existing-match-1"}]}},
                }
            ]
        }
        mock_get.return_value = mock_response

        result = pubg_client.get_new_matches(["player1"])

        assert result == []


class TestGetMatch:
    """Test cases for get_match method."""

    def test_get_match_empty_id_raises_error(self, pubg_client):
        """Test that empty match_id raises ValueError."""
        with pytest.raises(ValueError, match="match_id cannot be empty"):
            pubg_client.get_match("")

    @patch("requests.get")
    def test_get_match_success(self, mock_get, pubg_client):
        """Test successful match fetch."""
        match_id = "match-123"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"type": "match", "id": match_id}}
        mock_get.return_value = mock_response

        result = pubg_client.get_match(match_id)

        assert result["data"]["id"] == match_id

    @patch("requests.get")
    def test_get_match_uses_cache(self, mock_get, pubg_client):
        """Test that match responses are cached."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"id": "match-1"}}
        mock_get.return_value = mock_response

        # First call
        pubg_client.get_match("match-1")

        # Second call (should use cache)
        pubg_client.get_match("match-1")

        # Should only make one API call
        assert mock_get.call_count == 1

    @patch("requests.get")
    def test_get_match_not_found(self, mock_get, pubg_client):
        """Test 404 not found raises NotFoundError."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        with pytest.raises(NotFoundError):
            pubg_client.get_match("nonexistent")


class TestExtractMatchMetadata:
    """Test cases for extract_match_metadata method."""

    def test_extract_match_metadata_invalid_data_raises_error(self, pubg_client):
        """Test that invalid data raises ValueError."""
        with pytest.raises(ValueError, match="Invalid match data"):
            pubg_client.extract_match_metadata({})

        with pytest.raises(ValueError, match="Invalid match data"):
            pubg_client.extract_match_metadata({"data": None})

    def test_extract_match_metadata_success(self, pubg_client):
        """Test successful metadata extraction."""
        match_data = {
            "data": {
                "id": "match-123",
                "attributes": {
                    "mapName": "Baltic_Main",
                    "createdAt": "2024-01-01T12:00:00Z",
                    "gameMode": "squad-fpp",
                    "matchType": "official",
                },
                "relationships": {"assets": {"data": [{"id": "asset-1"}]}},
            },
            "included": [
                {
                    "type": "asset",
                    "id": "asset-1",
                    "attributes": {"URL": "https://telemetry-cdn.pubg.com/..."},
                }
            ],
        }

        result = pubg_client.extract_match_metadata(match_data)

        assert result["match_id"] == "match-123"
        assert result["map_name"] == "Erangel (Remastered)"  # Translated
        assert isinstance(result["match_datetime"], datetime)
        assert result["game_mode"] == "squad-fpp"
        assert result["game_type"] == "official"
        assert result["telemetry_url"] == "https://telemetry-cdn.pubg.com/..."

    def test_extract_match_metadata_missing_telemetry(self, pubg_client):
        """Test metadata extraction when telemetry URL missing."""
        match_data = {
            "data": {
                "id": "match-123",
                "attributes": {
                    "mapName": "Baltic_Main",
                    "createdAt": "2024-01-01T12:00:00Z",
                    "gameMode": "squad-fpp",
                    "matchType": "official",
                },
                "relationships": {
                    "assets": {"data": []}  # No assets
                },
            },
            "included": [],
        }

        result = pubg_client.extract_match_metadata(match_data)

        assert result["telemetry_url"] is None


class TestTransformMapName:
    """Test cases for transform_map_name method."""

    def test_transform_map_name_known_maps(self, pubg_client):
        """Test transformation of known map names."""
        assert pubg_client.transform_map_name("Baltic_Main") == "Erangel (Remastered)"
        assert pubg_client.transform_map_name("Desert_Main") == "Miramar"
        assert pubg_client.transform_map_name("Kiki_Main") == "Deston"
        assert pubg_client.transform_map_name("Range_Main") == "Camp Jackal"

    def test_transform_map_name_unknown_map_returns_original(self, pubg_client):
        """Test that unknown map names are returned as-is."""
        assert pubg_client.transform_map_name("Unknown_Map") == "Unknown_Map"

    def test_transform_map_name_empty_string(self, pubg_client):
        """Test that empty string is handled."""
        assert pubg_client.transform_map_name("") == ""


class TestCaching:
    """Test cases for caching functionality."""

    def test_clear_cache(self, pubg_client):
        """Test that clear_cache removes all cached items."""
        pubg_client._cache["test_key"] = {"data": {}, "time": datetime.now()}

        pubg_client.clear_cache()

        assert len(pubg_client._cache) == 0

    def test_cache_get_and_set(self, pubg_client):
        """Test cache get/set operations."""
        data = {"test": "data"}

        # Set cache
        pubg_client._set_cached("test_key", data)

        # Get from cache
        cached = pubg_client._get_cached("test_key")

        assert cached == data

    def test_cache_expiration(self, pubg_client):
        """Test that expired cache entries are removed."""
        old_time = datetime.now() - timedelta(seconds=400)
        pubg_client._cache["test_key"] = {"data": {"test": "data"}, "time": old_time}

        # Should return None and remove expired entry
        cached = pubg_client._get_cached("test_key")

        assert cached is None
        assert "test_key" not in pubg_client._cache


class TestRateLimiting:
    """Test cases for rate limiting behavior."""

    @patch("requests.get")
    @patch("time.sleep")
    def test_rate_limit_triggers_retry(self, mock_sleep, mock_get, pubg_client):
        """Test that 429 response triggers retry with backoff."""
        mock_response_429 = Mock()
        mock_response_429.status_code = 429

        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"data": []}

        mock_get.side_effect = [mock_response_429, mock_response_success]

        pubg_client.get_player_info(["player1"])

        assert mock_get.call_count == 2
        # With new pacing behavior, sleep is called twice:
        # 1. Retry backoff (1s)
        # 2. Pacing logic in select_key() (~6.9s for 10 RPM)
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 1  # First call: retry backoff

    @patch("requests.get")
    @patch("time.sleep")
    def test_rate_limit_exceeds_max_retries(self, mock_sleep, mock_get, pubg_client):
        """Test that repeated 429s raise RateLimitError."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        with pytest.raises(RateLimitError):
            pubg_client.get_player_info(["player1"])


class TestAPIKeyIntegration:
    """Test integration with APIKeyManager."""

    @patch("requests.get")
    def test_uses_api_key_from_manager(
        self, mock_get, mock_key_manager, mock_get_existing_match_ids
    ):
        """Test that client uses API key from manager."""
        client = PUBGClient(mock_key_manager, mock_get_existing_match_ids)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        client.get_player_info(["player1"])

        call_args = mock_get.call_args
        auth_header = call_args.kwargs["headers"]["Authorization"]
        assert "test_key_123" in auth_header

    @patch("requests.get")
    def test_records_request_with_manager(
        self, mock_get, mock_key_manager, mock_get_existing_match_ids
    ):
        """Test that successful requests are recorded in manager."""
        client = PUBGClient(mock_key_manager, mock_get_existing_match_ids)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        initial_count = len(mock_key_manager._keys[0].request_times)

        client.get_player_info(["player1"])

        final_count = len(mock_key_manager._keys[0].request_times)
        assert final_count == initial_count + 1


class TestHealthCheck:
    """Test cases for health_check method."""

    @patch("requests.get")
    def test_health_check_success(self, mock_get, pubg_client):
        """Test health check returns True on success."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        assert pubg_client.health_check() is True

    @patch("requests.get")
    def test_health_check_404_is_success(self, mock_get, pubg_client):
        """Test health check returns True even on 404."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        assert pubg_client.health_check() is True

    @patch("requests.get")
    def test_health_check_failure(self, mock_get, pubg_client):
        """Test health check returns False on error."""
        mock_get.side_effect = Timeout("Connection timeout")

        with patch("time.sleep"):
            assert pubg_client.health_check() is False
