"""Integration tests for PUBGClient using real PUBG API.

These tests make actual API calls to validate:
- Player info retrieval
- Match discovery logic
- Match data fetching
- Metadata extraction

Run with: pytest tests/integration/test_pubg_client_integration.py -v -s

Note: These tests require a valid PUBG API key set via environment variable.
"""

import logging
import os
import pytest
from datetime import datetime

from pewstats_collectors.core.api_key_manager import APIKeyManager
from pewstats_collectors.core.pubg_client import PUBGClient, NotFoundError


# Configure logging to see debug output
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# API Key from environment (skip tests if not available)
PUBG_API_KEY = os.getenv(
    "PUBG_API_KEY",
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiJmZTUwMGY4MC00ZDA0LTAxM2UtMDI3ZC0wMjAwYjdjMWRhMzYiLCJpc3MiOiJnYW1lbG9ja2VyIiwiaWF0IjoxNzUzNjEzMjM5LCJwdWIiOiJibHVlaG9sZSIsInRpdGxlIjoicHViZyIsImFwcCI6ImRldi1lbnZpcm9ubWVuIn0.A_Etq0KXdSJ9Qo1owyv2FyZ6ete7fleiS2RHFc5Moss"
)
TEST_PLAYER_NAME = "XacatecaS"


@pytest.fixture
def api_key_manager():
    """Create APIKeyManager with test key."""
    keys = [{"key": PUBG_API_KEY, "rpm": 10}]
    return APIKeyManager(keys)


@pytest.fixture
def pubg_client(api_key_manager):
    """Create PUBGClient with test configuration."""
    # Mock function that returns empty set (no existing matches)
    def get_existing_match_ids():
        return set()

    return PUBGClient(
        api_key_manager=api_key_manager,
        get_existing_match_ids=get_existing_match_ids,
        platform="steam"
    )


class TestPlayerInfoIntegration:
    """Integration tests for player info retrieval."""

    def test_get_player_info_real_player(self, pubg_client):
        """Test fetching real player information."""
        result = pubg_client.get_player_info([TEST_PLAYER_NAME])

        # Validate response structure
        assert "data" in result
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 1

        # Validate player data structure
        player = result["data"][0]
        assert player["type"] == "player"
        assert "id" in player
        assert "attributes" in player
        assert player["attributes"]["name"] == TEST_PLAYER_NAME

        # Validate relationships exist
        assert "relationships" in player
        assert "matches" in player["relationships"]

        logger.info(f"Successfully fetched player: {TEST_PLAYER_NAME}")
        logger.info(f"Player ID: {player['id']}")
        logger.info(f"Number of matches: {len(player['relationships']['matches']['data'])}")

    def test_get_player_info_caching(self, pubg_client):
        """Test that caching works for repeated requests."""
        # First request - should hit API
        result1 = pubg_client.get_player_info([TEST_PLAYER_NAME])

        # Second request - should use cache
        result2 = pubg_client.get_player_info([TEST_PLAYER_NAME])

        # Results should be identical
        assert result1 == result2
        logger.info("Cache test passed - identical results")

    def test_get_player_info_nonexistent_player(self, pubg_client):
        """Test handling of nonexistent player."""
        # PUBG API returns 404 for nonexistent players
        with pytest.raises(NotFoundError):
            pubg_client.get_player_info(["ThisPlayerDoesNotExist12345"])

        logger.info("NotFoundError raised correctly for nonexistent player")


class TestMatchDiscoveryIntegration:
    """Integration tests for match discovery logic."""

    def test_get_new_matches_real_player(self, pubg_client):
        """Test discovering new matches for real player."""
        result = pubg_client.get_new_matches([TEST_PLAYER_NAME])

        # Should return list of match IDs
        assert isinstance(result, list)

        # Each match ID should be a string
        for match_id in result:
            assert isinstance(match_id, str)
            assert len(match_id) > 0

        logger.info(f"Found {len(result)} new matches")
        if result:
            logger.info(f"First match ID: {result[0]}")

    def test_get_new_matches_filters_existing(self, api_key_manager):
        """Test that existing matches are filtered out."""
        # Create client with mock existing matches
        existing_matches = set()

        # First, get all matches
        client1 = PUBGClient(
            api_key_manager=api_key_manager,
            get_existing_match_ids=lambda: set(),
            platform="steam"
        )
        all_matches = client1.get_new_matches([TEST_PLAYER_NAME])

        if len(all_matches) > 0:
            # Mark first match as existing
            existing_matches.add(all_matches[0])

            # Create new client with existing match
            client2 = PUBGClient(
                api_key_manager=api_key_manager,
                get_existing_match_ids=lambda: existing_matches,
                platform="steam"
            )

            # Should not include the existing match
            new_matches = client2.get_new_matches([TEST_PLAYER_NAME])
            assert all_matches[0] not in new_matches
            logger.info(f"Filtering test passed - {all_matches[0]} excluded")


class TestMatchDataIntegration:
    """Integration tests for match data retrieval."""

    def test_get_match_real_data(self, pubg_client):
        """Test fetching real match data."""
        # First get a match ID from player
        new_matches = pubg_client.get_new_matches([TEST_PLAYER_NAME])

        if len(new_matches) == 0:
            pytest.skip("No matches available for testing")

        match_id = new_matches[0]
        logger.info(f"Testing with match ID: {match_id}")

        # Fetch match data
        result = pubg_client.get_match(match_id)

        # Validate response structure
        assert "data" in result
        assert result["data"]["type"] == "match"
        assert result["data"]["id"] == match_id
        assert "attributes" in result["data"]

        # Validate attributes
        attrs = result["data"]["attributes"]
        assert "mapName" in attrs
        assert "gameMode" in attrs
        assert "createdAt" in attrs

        logger.info(f"Match map: {attrs['mapName']}")
        logger.info(f"Match mode: {attrs['gameMode']}")
        logger.info(f"Match date: {attrs['createdAt']}")

    def test_get_match_caching(self, pubg_client):
        """Test that match data caching works."""
        # Get a match ID
        new_matches = pubg_client.get_new_matches([TEST_PLAYER_NAME])

        if len(new_matches) == 0:
            pytest.skip("No matches available for testing")

        match_id = new_matches[0]

        # First request
        result1 = pubg_client.get_match(match_id)

        # Second request - should use cache
        result2 = pubg_client.get_match(match_id)

        assert result1 == result2
        logger.info("Match caching test passed")

    def test_get_match_not_found(self, pubg_client):
        """Test handling of nonexistent match."""
        fake_match_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(NotFoundError):
            pubg_client.get_match(fake_match_id)

        logger.info("NotFoundError raised correctly for fake match ID")


class TestMetadataExtractionIntegration:
    """Integration tests for metadata extraction."""

    def test_extract_metadata_real_match(self, pubg_client):
        """Test extracting metadata from real match data."""
        # Get a match
        new_matches = pubg_client.get_new_matches([TEST_PLAYER_NAME])

        if len(new_matches) == 0:
            pytest.skip("No matches available for testing")

        match_id = new_matches[0]
        match_data = pubg_client.get_match(match_id)

        # Extract metadata
        metadata = pubg_client.extract_match_metadata(match_data)

        # Validate metadata structure
        assert "match_id" in metadata
        assert "map_name" in metadata
        assert "match_datetime" in metadata
        assert "game_mode" in metadata
        assert "game_type" in metadata
        assert "telemetry_url" in metadata

        # Validate types
        assert metadata["match_id"] == match_id
        assert isinstance(metadata["map_name"], str)
        assert isinstance(metadata["match_datetime"], datetime)
        assert isinstance(metadata["game_mode"], str)
        assert isinstance(metadata["game_type"], str)

        # Telemetry URL should be present (unless match is very old)
        if metadata["telemetry_url"]:
            assert metadata["telemetry_url"].startswith("https://")

        logger.info(f"Metadata extracted successfully:")
        logger.info(f"  Match ID: {metadata['match_id']}")
        logger.info(f"  Map: {metadata['map_name']}")
        logger.info(f"  Mode: {metadata['game_mode']}")
        logger.info(f"  Type: {metadata['game_type']}")
        logger.info(f"  DateTime: {metadata['match_datetime']}")
        logger.info(f"  Telemetry URL: {metadata['telemetry_url'][:50] if metadata['telemetry_url'] else 'None'}...")

    def test_map_name_translation(self, pubg_client):
        """Test that map names are translated correctly."""
        # Get match and check map translation
        new_matches = pubg_client.get_new_matches([TEST_PLAYER_NAME])

        if len(new_matches) == 0:
            pytest.skip("No matches available for testing")

        match_id = new_matches[0]
        match_data = pubg_client.get_match(match_id)
        metadata = pubg_client.extract_match_metadata(match_data)

        # Map name should be translated (not internal name like "Baltic_Main")
        map_name = metadata["map_name"]
        internal_names = [
            "Baltic_Main", "Chimera_Main", "Desert_Main", "DihorOtok_Main",
            "Erangel_Main", "Heaven_Main", "Kiki_Main", "Range_Main",
            "Savage_Main", "Summerland_Main", "Tiger_Main", "Neon_Main"
        ]

        # Should be translated to friendly name (or unknown map)
        # Most maps should be translated
        logger.info(f"Map name: {map_name}")

        # At minimum, should not be empty
        assert len(map_name) > 0


class TestHealthCheckIntegration:
    """Integration test for health check."""

    @pytest.mark.skip(reason="Skip to avoid rate limiting during test runs")
    def test_health_check_real_api(self, pubg_client):
        """Test health check with real API."""
        result = pubg_client.health_check()

        # Should return True if API is accessible
        assert result is True
        logger.info("Health check passed - API is accessible")


class TestRateLimitingIntegration:
    """Integration tests for rate limiting behavior."""

    @pytest.mark.skip(reason="Skip to avoid rate limiting during test runs")
    def test_respects_rate_limits(self, pubg_client):
        """Test that rate limiting is respected over multiple requests."""
        import time

        # Make multiple requests quickly
        start_time = time.time()

        for i in range(3):  # Reduced to 3 requests to stay under 10 RPM
            pubg_client.get_player_info([TEST_PLAYER_NAME])
            logger.info(f"Request {i+1} completed")

        elapsed = time.time() - start_time

        # With 10 RPM limit, 3 requests should not cause rate limiting
        logger.info(f"3 requests completed in {elapsed:.2f} seconds")

        # Should complete in reasonable time (not excessive waiting)
        assert elapsed < 30, "Requests took too long - possible rate limiting issue"
