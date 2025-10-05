"""
Unit tests for Telemetry Processing Worker
"""

import gzip
import json
import os
import pytest
import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch, call

from pewstats_collectors.workers.telemetry_processing_worker import (
    TelemetryProcessingWorker,
    get_event_type,
    get_nested,
)


class TestHelperFunctions:
    """Test helper functions"""

    def test_get_event_type_with_underscore_t(self):
        """Should get event type from _T field"""
        event = {"_T": "LogParachuteLanding", "data": "test"}
        assert get_event_type(event) == "LogParachuteLanding"

    def test_get_event_type_with_type(self):
        """Should get event type from type field"""
        event = {"type": "LogPlayerKillV2", "data": "test"}
        assert get_event_type(event) == "LogPlayerKillV2"

    def test_get_event_type_with_event_type(self):
        """Should get event type from event_type field"""
        event = {"event_type": "LogGameStatePeriodic", "data": "test"}
        assert get_event_type(event) == "LogGameStatePeriodic"

    def test_get_event_type_priority(self):
        """Should prioritize _T over type over event_type"""
        event = {"_T": "First", "type": "Second", "event_type": "Third"}
        assert get_event_type(event) == "First"

    def test_get_event_type_none(self):
        """Should return None if no type field"""
        event = {"data": "test"}
        assert get_event_type(event) is None

    def test_get_nested_simple(self):
        """Should get simple nested value"""
        obj = {"a": {"b": {"c": 123}}}
        assert get_nested(obj, "a.b.c") == 123

    def test_get_nested_with_default(self):
        """Should return default for missing path"""
        obj = {"a": {"b": 1}}
        assert get_nested(obj, "a.c.d", default="default") == "default"

    def test_get_nested_none_value(self):
        """Should return default for None value"""
        obj = {"a": {"b": None}}
        assert get_nested(obj, "a.b", default="default") == "default"

    def test_get_nested_non_dict(self):
        """Should return default for non-dict in path"""
        obj = {"a": "string"}
        assert get_nested(obj, "a.b.c", default="default") == "default"

    def test_get_nested_deep_path(self):
        """Should handle deep nested paths"""
        obj = {"a": {"b": {"c": {"d": {"e": "value"}}}}}
        assert get_nested(obj, "a.b.c.d.e") == "value"


class TestTelemetryProcessingWorker:
    """Test TelemetryProcessingWorker class"""

    @pytest.fixture
    def mock_database_manager(self):
        """Mock database manager"""
        return Mock()

    @pytest.fixture
    def worker(self, mock_database_manager):
        """Create worker instance"""
        return TelemetryProcessingWorker(
            database_manager=mock_database_manager,
            worker_id="test-worker-001",
        )

    @pytest.fixture
    def sample_telemetry_events(self):
        """Sample telemetry events"""
        return [
            {
                "_T": "LogParachuteLanding",
                "character": {
                    "accountId": "account.abc123",
                    "name": "TestPlayer1",
                    "teamId": 1,
                    "location": {"x": 100.5, "y": 200.5, "z": 300.5}
                },
                "common": {"isGame": 1.0}
            },
            {
                "_T": "LogParachuteLanding",
                "character": {
                    "accountId": "account.xyz789",
                    "name": "TestPlayer2",
                    "teamId": 2,
                    "location": {"x": 150.5, "y": 250.5, "z": 350.5}
                },
                "common": {"isGame": 1.0}
            },
            {
                "_T": "LogPlayerKillV2",
                "victim": {"name": "SomeVictim"},
                "data": "other event"
            }
        ]

    def test_initialization(self, worker):
        """Should initialize with correct attributes"""
        assert worker.worker_id == "test-worker-001"
        assert worker.processed_count == 0
        assert worker.error_count == 0

    def test_process_message_missing_match_id(self, worker):
        """Should fail if message missing match_id"""
        result = worker.process_message({})

        assert result["success"] is False
        assert "match_id" in result["error"]
        assert worker.error_count == 1

    def test_process_message_missing_file_path(self, worker):
        """Should fail if message missing file_path"""
        result = worker.process_message({"match_id": "match-123"})

        assert result["success"] is False
        assert "file_path" in result["error"]
        assert worker.error_count == 1

    def test_extract_landings(self, worker, sample_telemetry_events):
        """Should extract landing events correctly"""
        match_data = {
            "map_name": "Erangel",
            "game_mode": "squad-fpp",
            "match_datetime": "2024-01-15T14:30:45Z"
        }

        landings = worker.extract_landings(
            sample_telemetry_events,
            "match-123",
            match_data
        )

        assert len(landings) == 2

        # Check first landing
        assert landings[0]["match_id"] == "match-123"
        assert landings[0]["player_id"] == "account.abc123"
        assert landings[0]["player_name"] == "TestPlayer1"
        assert landings[0]["team_id"] == 1
        assert landings[0]["x_coordinate"] == 100.5
        assert landings[0]["y_coordinate"] == 200.5
        assert landings[0]["z_coordinate"] == 300.5
        assert landings[0]["is_game"] == 1.0
        assert landings[0]["map_name"] == "Erangel"
        assert landings[0]["game_mode"] == "squad-fpp"

    def test_extract_landings_filters_invalid_player_ids(self, worker):
        """Should filter out invalid player IDs"""
        events = [
            {
                "_T": "LogParachuteLanding",
                "character": {
                    "accountId": "invalid_id",  # Doesn't start with "account"
                    "name": "Invalid",
                    "location": {"x": 1, "y": 1, "z": 1}
                },
                "common": {"isGame": 1.0}
            }
        ]

        landings = worker.extract_landings(events, "match-123", {})
        assert len(landings) == 0

    def test_extract_landings_filters_lobby_events(self, worker):
        """Should filter out lobby events (is_game < 1)"""
        events = [
            {
                "_T": "LogParachuteLanding",
                "character": {
                    "accountId": "account.test",
                    "name": "Test",
                    "location": {"x": 1, "y": 1, "z": 1}
                },
                "common": {"isGame": 0.0}  # Lobby
            }
        ]

        landings = worker.extract_landings(events, "match-123", {})
        assert len(landings) == 0

    def test_extract_landings_deduplicates_by_player(self, worker):
        """Should deduplicate landings by player_id"""
        events = [
            {
                "_T": "LogParachuteLanding",
                "character": {
                    "accountId": "account.player1",
                    "name": "Player1",
                    "location": {"x": 100, "y": 100, "z": 100}
                },
                "common": {"isGame": 1.0}
            },
            {
                "_T": "LogParachuteLanding",
                "character": {
                    "accountId": "account.player1",  # Same player
                    "name": "Player1",
                    "location": {"x": 200, "y": 200, "z": 200}  # Different location
                },
                "common": {"isGame": 1.0}
            }
        ]

        landings = worker.extract_landings(events, "match-123", {})
        assert len(landings) == 1  # Only first landing kept

    def test_extract_landings_handles_alternate_is_game_field(self, worker):
        """Should handle alternate is_game field name"""
        events = [
            {
                "_T": "LogParachuteLanding",
                "character": {
                    "accountId": "account.test",
                    "name": "Test",
                    "location": {"x": 1, "y": 1, "z": 1}
                },
                "common": {"is_game": 1.0}  # Alternate field name
            }
        ]

        landings = worker.extract_landings(events, "match-123", {})
        assert len(landings) == 1

    def test_get_stats(self, worker):
        """Should return correct statistics"""
        worker.processed_count = 10
        worker.error_count = 2

        stats = worker.get_stats()

        assert stats["worker_id"] == "test-worker-001"
        assert stats["worker_type"] == "TelemetryProcessingWorker"
        assert stats["processed_count"] == 10
        assert stats["error_count"] == 2
        assert stats["success_rate"] == 10 / 12

    def test_read_telemetry_file(self, worker, tmp_path, sample_telemetry_events):
        """Should read and parse gzipped telemetry file"""
        # Create test file
        file_path = tmp_path / "raw.json.gz"
        with gzip.open(file_path, 'wt', encoding='utf-8') as f:
            json.dump(sample_telemetry_events, f)

        # Read it
        events = worker._read_telemetry_file(str(file_path))

        assert len(events) == 3
        assert events[0]["_T"] == "LogParachuteLanding"

    def test_read_telemetry_file_not_found(self, worker):
        """Should raise error if file not found"""
        with pytest.raises(Exception):
            worker._read_telemetry_file("/nonexistent/file.json.gz")

    def test_process_message_success(
        self, worker, mock_database_manager, tmp_path, sample_telemetry_events
    ):
        """Should successfully process telemetry"""
        # Create test file
        file_path = tmp_path / "raw.json.gz"
        with gzip.open(file_path, 'wt', encoding='utf-8') as f:
            json.dump(sample_telemetry_events, f)

        mock_database_manager.insert_landings.return_value = 2
        mock_database_manager.update_match_processing_flags.return_value = True
        mock_database_manager.update_match_status.return_value = True

        # Execute
        result = worker.process_message({
            "match_id": "match-123",
            "file_path": str(file_path),
            "map_name": "Erangel",
            "game_mode": "squad-fpp",
        })

        # Verify
        assert result["success"] is True
        assert worker.processed_count == 1
        assert worker.error_count == 0

        # Verify database calls
        mock_database_manager.insert_landings.assert_called_once()
        landings = mock_database_manager.insert_landings.call_args[0][0]
        assert len(landings) == 2

        mock_database_manager.update_match_processing_flags.assert_called_once()
        mock_database_manager.update_match_status.assert_called_once_with(
            "match-123", "completed", None
        )

    def test_process_message_empty_events(
        self, worker, mock_database_manager, tmp_path
    ):
        """Should fail if no events in file"""
        # Create empty file
        file_path = tmp_path / "raw.json.gz"
        with gzip.open(file_path, 'wt', encoding='utf-8') as f:
            json.dump([], f)

        result = worker.process_message({
            "match_id": "match-123",
            "file_path": str(file_path),
        })

        assert result["success"] is False
        assert "No events" in result["error"]
        assert worker.error_count == 1

    def test_process_message_file_read_error(self, worker):
        """Should handle file read errors"""
        result = worker.process_message({
            "match_id": "match-123",
            "file_path": "/nonexistent/file.json.gz",
        })

        assert result["success"] is False
        assert worker.error_count == 1

    def test_process_message_database_error(
        self, worker, mock_database_manager, tmp_path, sample_telemetry_events
    ):
        """Should handle database errors"""
        # Create test file
        file_path = tmp_path / "raw.json.gz"
        with gzip.open(file_path, 'wt', encoding='utf-8') as f:
            json.dump(sample_telemetry_events, f)

        # Database insert fails
        mock_database_manager.insert_landings.side_effect = Exception("DB error")

        result = worker.process_message({
            "match_id": "match-123",
            "file_path": str(file_path),
            "map_name": "Erangel",
        })

        assert result["success"] is False
        assert "DB error" in result["error"]
        assert worker.error_count == 1

        # Should update match status to failed
        mock_database_manager.update_match_status.assert_called_with(
            "match-123", "failed", "Telemetry processing failed: DB error"
        )
