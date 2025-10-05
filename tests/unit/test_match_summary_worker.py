"""
Unit tests for Match Summary Worker
"""

import pytest
from datetime import datetime
from unittest.mock import Mock
from pewstats_collectors.workers.match_summary_worker import (
    MatchSummaryWorker,
    transform_map_name,
    parse_datetime,
)


class TestHelperFunctions:
    """Test helper functions"""

    def test_transform_map_name_known_map(self):
        """Should transform known internal map names"""
        assert transform_map_name("Baltic_Main") == "Erangel"
        assert transform_map_name("Desert_Main") == "Miramar"
        assert transform_map_name("DihorOtok_Main") == "Vikendi"
        assert transform_map_name("Savage_Main") == "Sanhok"
        assert transform_map_name("Kiki_Main") == "Deston"

    def test_transform_map_name_unknown_map(self):
        """Should return original name for unknown maps"""
        assert transform_map_name("Unknown_Map") == "Unknown_Map"

    def test_transform_map_name_none(self):
        """Should return None for None input"""
        assert transform_map_name(None) is None

    def test_parse_datetime_valid_iso8601(self):
        """Should parse valid ISO 8601 datetime with Z suffix"""
        result = parse_datetime("2024-01-15T14:30:45Z")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45

    def test_parse_datetime_valid_with_timezone(self):
        """Should parse valid ISO 8601 datetime with timezone"""
        result = parse_datetime("2024-01-15T14:30:45+00:00")
        assert isinstance(result, datetime)
        assert result.year == 2024

    def test_parse_datetime_invalid_format(self):
        """Should return None for invalid format"""
        assert parse_datetime("invalid-datetime") is None
        assert parse_datetime("not a date") is None

    def test_parse_datetime_none(self):
        """Should return None for None input"""
        assert parse_datetime(None) is None


class TestMatchSummaryWorker:
    """Test MatchSummaryWorker class"""

    @pytest.fixture
    def mock_pubg_client(self):
        """Mock PUBG client"""
        return Mock()

    @pytest.fixture
    def mock_database_manager(self):
        """Mock database manager"""
        return Mock()

    @pytest.fixture
    def mock_rabbitmq_publisher(self):
        """Mock RabbitMQ publisher"""
        return Mock()

    @pytest.fixture
    def worker(self, mock_pubg_client, mock_database_manager, mock_rabbitmq_publisher):
        """Create worker instance"""
        return MatchSummaryWorker(
            pubg_client=mock_pubg_client,
            database_manager=mock_database_manager,
            rabbitmq_publisher=mock_rabbitmq_publisher,
            worker_id="test-worker-001",
        )

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

    def test_extract_telemetry_url_valid_data(self, worker):
        """Should extract telemetry URL from valid match data"""
        match_data = {
            "data": {"relationships": {"assets": {"data": [{"id": "asset-123", "type": "asset"}]}}},
            "included": [
                {
                    "type": "asset",
                    "id": "asset-123",
                    "attributes": {
                        "URL": "https://telemetry-cdn.pubg.com/bluehole-pubg/pc-2018/2024/01/15/match.json"
                    },
                }
            ],
        }

        url = worker.extract_telemetry_url(match_data)
        assert url == "https://telemetry-cdn.pubg.com/bluehole-pubg/pc-2018/2024/01/15/match.json"

    def test_extract_telemetry_url_missing_assets(self, worker):
        """Should return None if no assets in data"""
        match_data = {"data": {"relationships": {}}}

        url = worker.extract_telemetry_url(match_data)
        assert url is None

    def test_extract_telemetry_url_asset_not_in_included(self, worker):
        """Should return None if asset not found in included"""
        match_data = {
            "data": {"relationships": {"assets": {"data": [{"id": "asset-123"}]}}},
            "included": [],
        }

        url = worker.extract_telemetry_url(match_data)
        assert url is None

    def test_create_roster_lookup(self, worker):
        """Should create correct roster lookup mapping"""
        rosters = [
            {
                "attributes": {"stats": {"teamId": 1, "rank": 2}, "won": "true"},
                "relationships": {
                    "participants": {"data": [{"id": "participant-1"}, {"id": "participant-2"}]}
                },
            },
            {
                "attributes": {"stats": {"teamId": 2, "rank": 5}, "won": "false"},
                "relationships": {"participants": {"data": [{"id": "participant-3"}]}},
            },
        ]

        lookup = worker.create_roster_lookup(rosters)

        assert lookup["participant-1"]["team_id"] == 1
        assert lookup["participant-1"]["team_rank"] == 2
        assert lookup["participant-1"]["won"] is True

        assert lookup["participant-2"]["team_id"] == 1
        assert lookup["participant-3"]["team_id"] == 2
        assert lookup["participant-3"]["won"] is False

    def test_create_roster_lookup_empty(self, worker):
        """Should handle empty rosters list"""
        lookup = worker.create_roster_lookup([])
        assert lookup == {}

    def test_extract_participant_data(self, worker):
        """Should extract all participant fields correctly"""
        participant = {
            "id": "participant-123",
            "attributes": {
                "stats": {
                    "playerId": "account.abc123",
                    "name": "TestPlayer",
                    "kills": 5,
                    "assists": 2,
                    "DBNOs": 3,
                    "damageDealt": 500.5,
                    "timeSurvived": 1500,
                    "headshotKills": 2,
                    "longestKill": 150.25,
                    "heals": 5,
                    "boosts": 3,
                    "revives": 1,
                    "rideDistance": 1000.0,
                    "swimDistance": 50.0,
                    "walkDistance": 2000.0,
                    "weaponsAcquired": 8,
                    "vehicleDestroys": 0,
                    "roadKills": 0,
                    "teamKills": 0,
                    "killStreaks": 1,
                    "killPlace": 3,
                    "winPlace": 5,
                    "deathType": "byplayer",
                }
            },
        }

        match_info = {
            "mapName": "Baltic_Main",
            "gameMode": "squad-fpp",
            "duration": 1800,
            "createdAt": "2024-01-15T14:30:45Z",
            "shardId": "steam",
            "isCustomMatch": False,
            "matchType": "official",
            "seasonState": "progress",
            "titleId": "pubg",
        }

        roster_lookup = {"participant-123": {"team_id": 5, "team_rank": 2, "won": False}}

        data = worker.extract_participant_data(participant, match_info, "match-123", roster_lookup)

        assert data["match_id"] == "match-123"
        assert data["participant_id"] == "participant-123"
        assert data["player_id"] == "account.abc123"
        assert data["player_name"] == "TestPlayer"
        assert data["team_id"] == 5
        assert data["team_rank"] == 2
        assert data["won"] is False
        assert data["map_name"] == "Erangel"  # Transformed
        assert data["game_mode"] == "squad-fpp"
        assert data["kills"] == 5
        assert data["assists"] == 2
        assert data["dbnos"] == 3
        assert data["damage_dealt"] == 500.5
        assert data["time_survived"] == 1500
        assert data["headshot_kills"] == 2
        assert isinstance(data["created_at"], datetime)

    def test_extract_participant_data_missing_team_info(self, worker):
        """Should handle missing team info gracefully"""
        participant = {
            "id": "participant-123",
            "attributes": {"stats": {"playerId": "account.abc", "name": "Test"}},
        }
        match_info = {"mapName": "Baltic_Main", "createdAt": "2024-01-15T14:30:45Z"}
        roster_lookup = {}

        data = worker.extract_participant_data(participant, match_info, "match-123", roster_lookup)

        assert data["team_id"] is None
        assert data["team_rank"] is None
        assert data["won"] is False

    def test_parse_match_summaries_complete(self, worker):
        """Should parse complete match data into summaries"""
        match_data = {
            "data": {
                "id": "match-123",
                "attributes": {
                    "mapName": "Baltic_Main",
                    "gameMode": "squad-fpp",
                    "duration": 1800,
                    "createdAt": "2024-01-15T14:30:45Z",
                },
            },
            "included": [
                {
                    "type": "participant",
                    "id": "participant-1",
                    "attributes": {
                        "stats": {"playerId": "account.player1", "name": "Player1", "kills": 5}
                    },
                },
                {
                    "type": "participant",
                    "id": "participant-2",
                    "attributes": {
                        "stats": {"playerId": "account.player2", "name": "Player2", "kills": 3}
                    },
                },
                {
                    "type": "roster",
                    "attributes": {"stats": {"teamId": 1, "rank": 1}, "won": "true"},
                    "relationships": {
                        "participants": {"data": [{"id": "participant-1"}, {"id": "participant-2"}]}
                    },
                },
            ],
        }

        summaries = worker.parse_match_summaries(match_data)

        assert len(summaries) == 2
        assert summaries[0]["player_name"] == "Player1"
        assert summaries[1]["player_name"] == "Player2"
        assert summaries[0]["team_id"] == 1
        assert summaries[0]["won"] is True

    def test_parse_match_summaries_no_participants(self, worker):
        """Should return empty list if no participants"""
        match_data = {"data": {"id": "match-123", "attributes": {}}, "included": []}

        summaries = worker.parse_match_summaries(match_data)
        assert summaries == []

    def test_match_summaries_exist_true(self, worker, mock_database_manager):
        """Should return True if summaries exist"""
        mock_database_manager.execute_query.return_value = [{"count": 5}]

        result = worker.match_summaries_exist("match-123")
        assert result is True

    def test_match_summaries_exist_false(self, worker, mock_database_manager):
        """Should return False if no summaries"""
        mock_database_manager.execute_query.return_value = [{"count": 0}]

        result = worker.match_summaries_exist("match-123")
        assert result is False

    def test_match_summaries_exist_error(self, worker, mock_database_manager):
        """Should return False on database error"""
        mock_database_manager.execute_query.side_effect = Exception("DB error")

        result = worker.match_summaries_exist("match-123")
        assert result is False

    def test_get_stats(self, worker):
        """Should return correct statistics"""
        worker.processed_count = 10
        worker.error_count = 2

        stats = worker.get_stats()

        assert stats["worker_id"] == "test-worker-001"
        assert stats["worker_type"] == "MatchSummaryWorker"
        assert stats["processed_count"] == 10
        assert stats["error_count"] == 2
        assert stats["success_rate"] == 10 / 12

    def test_get_stats_zero_division(self, worker):
        """Should handle zero division in success rate"""
        stats = worker.get_stats()
        assert stats["success_rate"] == 0

    def test_process_message_success(
        self, worker, mock_pubg_client, mock_database_manager, mock_rabbitmq_publisher
    ):
        """Should successfully process complete match"""
        # Setup mocks
        mock_database_manager.execute_query.return_value = [{"count": 0}]  # No existing summaries
        mock_database_manager.insert_match_summaries.return_value = 2

        mock_pubg_client.get_match_data.return_value = {
            "data": {
                "id": "match-123",
                "attributes": {
                    "mapName": "Baltic_Main",
                    "gameMode": "squad-fpp",
                    "createdAt": "2024-01-15T14:30:45Z",
                },
                "relationships": {"assets": {"data": [{"id": "asset-1"}]}},
            },
            "included": [
                {
                    "type": "asset",
                    "id": "asset-1",
                    "attributes": {"URL": "https://telemetry.pubg.com/match.json"},
                },
                {
                    "type": "participant",
                    "id": "p1",
                    "attributes": {"stats": {"playerId": "a1", "name": "Player1"}},
                },
                {
                    "type": "participant",
                    "id": "p2",
                    "attributes": {"stats": {"playerId": "a2", "name": "Player2"}},
                },
                {
                    "type": "roster",
                    "attributes": {"stats": {"teamId": 1, "rank": 1}, "won": "true"},
                    "relationships": {"participants": {"data": [{"id": "p1"}, {"id": "p2"}]}},
                },
            ],
        }

        mock_rabbitmq_publisher.publish_message.return_value = True

        # Execute
        result = worker.process_message({"match_id": "match-123"})

        # Verify
        assert result["success"] is True
        assert worker.processed_count == 1
        assert worker.error_count == 0
        mock_database_manager.insert_match_summaries.assert_called_once()
        mock_rabbitmq_publisher.publish_message.assert_called_once()

    def test_process_message_summaries_already_exist(
        self, worker, mock_pubg_client, mock_database_manager, mock_rabbitmq_publisher
    ):
        """Should handle existing summaries (idempotency)"""
        # Summaries already exist
        mock_database_manager.execute_query.return_value = [{"count": 2}]

        mock_pubg_client.get_match_data.return_value = {
            "data": {
                "id": "match-123",
                "attributes": {
                    "mapName": "Baltic_Main",
                    "gameMode": "squad-fpp",
                    "createdAt": "2024-01-15T14:30:45Z",
                },
                "relationships": {"assets": {"data": [{"id": "asset-1"}]}},
            },
            "included": [
                {
                    "type": "asset",
                    "id": "asset-1",
                    "attributes": {"URL": "https://telemetry.pubg.com/match.json"},
                }
            ],
        }

        mock_rabbitmq_publisher.publish_message.return_value = True

        # Execute
        result = worker.process_message({"match_id": "match-123"})

        # Verify - should NOT insert summaries, but still publish
        assert result["success"] is True
        mock_database_manager.insert_match_summaries.assert_not_called()
        mock_rabbitmq_publisher.publish_message.assert_called_once()

    def test_process_message_missing_telemetry_url(
        self, worker, mock_pubg_client, mock_database_manager
    ):
        """Should fail if telemetry URL cannot be extracted"""
        mock_database_manager.execute_query.return_value = [{"count": 0}]

        # Match data missing telemetry asset
        mock_pubg_client.get_match_data.return_value = {
            "data": {"id": "match-123", "attributes": {}},
            "included": [],
        }

        result = worker.process_message({"match_id": "match-123"})

        assert result["success"] is False
        assert "telemetry URL" in result["error"]
        assert worker.error_count == 1

    def test_process_message_no_participants(self, worker, mock_pubg_client, mock_database_manager):
        """Should fail if no participants found"""
        mock_database_manager.execute_query.return_value = [{"count": 0}]

        mock_pubg_client.get_match_data.return_value = {
            "data": {"id": "match-123", "relationships": {"assets": {"data": [{"id": "asset-1"}]}}},
            "included": [
                {
                    "type": "asset",
                    "id": "asset-1",
                    "attributes": {"URL": "https://telemetry.pubg.com/match.json"},
                }
            ],
        }

        result = worker.process_message({"match_id": "match-123"})

        assert result["success"] is False
        assert "participant" in result["error"].lower()

    def test_process_message_publish_failure(
        self, worker, mock_pubg_client, mock_database_manager, mock_rabbitmq_publisher
    ):
        """Should fail if publishing to queue fails"""
        mock_database_manager.execute_query.return_value = [{"count": 0}]
        mock_database_manager.insert_match_summaries.return_value = 2

        mock_pubg_client.get_match_data.return_value = {
            "data": {
                "id": "match-123",
                "attributes": {"mapName": "Baltic_Main", "createdAt": "2024-01-15T14:30:45Z"},
                "relationships": {"assets": {"data": [{"id": "asset-1"}]}},
            },
            "included": [
                {
                    "type": "asset",
                    "id": "asset-1",
                    "attributes": {"URL": "https://telemetry.pubg.com/match.json"},
                },
                {
                    "type": "participant",
                    "id": "p1",
                    "attributes": {"stats": {"playerId": "a1", "name": "P1"}},
                },
                {
                    "type": "roster",
                    "attributes": {"stats": {"teamId": 1, "rank": 1}, "won": "true"},
                    "relationships": {"participants": {"data": [{"id": "p1"}]}},
                },
            ],
        }

        # Publish fails
        mock_rabbitmq_publisher.publish_message.return_value = False

        result = worker.process_message({"match_id": "match-123"})

        assert result["success"] is False
        assert "publish" in result["error"].lower()
        assert worker.error_count == 1

    def test_process_message_exception(self, worker, mock_pubg_client, mock_database_manager):
        """Should handle exceptions gracefully"""
        mock_database_manager.execute_query.return_value = [{"count": 0}]
        mock_pubg_client.get_match_data.side_effect = Exception("API error")

        result = worker.process_message({"match_id": "match-123"})

        assert result["success"] is False
        assert "API error" in result["error"]
        assert worker.error_count == 1
