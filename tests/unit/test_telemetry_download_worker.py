"""
Unit tests for Telemetry Download Worker
"""

import gzip
import os
import pytest
from unittest.mock import Mock, patch

from pewstats_collectors.workers.telemetry_download_worker import (
    TelemetryDownloadWorker,
    is_gzipped,
)


class TestHelperFunctions:
    """Test helper functions"""

    def test_is_gzipped_true(self, tmp_path):
        """Should detect gzipped files"""
        gz_file = tmp_path / "test.json.gz"
        with gzip.open(gz_file, 'wb') as f:
            f.write(b'{"test": "data"}')

        assert is_gzipped(str(gz_file)) is True

    def test_is_gzipped_false(self, tmp_path):
        """Should detect non-gzipped files"""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        assert is_gzipped(str(json_file)) is False

    def test_is_gzipped_nonexistent(self):
        """Should return False for nonexistent files"""
        assert is_gzipped("/nonexistent/file.json.gz") is False


class TestTelemetryDownloadWorker:
    """Test TelemetryDownloadWorker class"""

    @pytest.fixture
    def mock_rabbitmq_publisher(self):
        """Mock RabbitMQ publisher"""
        return Mock()

    @pytest.fixture
    def tmp_data_path(self, tmp_path):
        """Temporary data path for tests"""
        return str(tmp_path / "telemetry")

    @pytest.fixture
    def worker(self, mock_rabbitmq_publisher, tmp_data_path):
        """Create worker instance"""
        return TelemetryDownloadWorker(
            rabbitmq_publisher=mock_rabbitmq_publisher,
            worker_id="test-worker-001",
            data_path=tmp_data_path,
        )

    def test_initialization(self, worker, tmp_data_path):
        """Should initialize with correct attributes"""
        assert worker.worker_id == "test-worker-001"
        assert worker.data_path == tmp_data_path
        assert worker.processed_count == 0
        assert worker.error_count == 0
        assert os.path.exists(tmp_data_path)

    def test_process_message_missing_match_id(self, worker):
        """Should fail if message missing match_id"""
        result = worker.process_message({})

        assert result["success"] is False
        assert "match_id" in result["error"]
        assert worker.error_count == 1

    def test_process_message_missing_telemetry_url(self, worker):
        """Should fail if message missing telemetry_url"""
        result = worker.process_message({"match_id": "match-123"})

        assert result["success"] is False
        assert "telemetry_url" in result["error"]
        assert worker.error_count == 1

    def test_telemetry_exists_true(self, worker):
        """Should return True if file exists"""
        match_id = "match-123"
        match_dir = os.path.join(worker.data_path, f"matchID={match_id}")
        os.makedirs(match_dir, exist_ok=True)

        file_path = os.path.join(match_dir, "raw.json.gz")
        with open(file_path, 'w') as f:
            f.write("test data")

        assert worker.telemetry_exists(match_id) is True

    def test_telemetry_exists_false(self, worker):
        """Should return False if file doesn't exist"""
        assert worker.telemetry_exists("match-123") is False

    def test_get_file_path(self, worker):
        """Should return correct file path"""
        path = worker._get_file_path("match-123")
        expected = os.path.join(worker.data_path, "matchID=match-123", "raw.json.gz")
        assert path == expected

    def test_get_stats(self, worker):
        """Should return correct statistics"""
        worker.processed_count = 10
        worker.error_count = 2

        stats = worker.get_stats()

        assert stats["worker_id"] == "test-worker-001"
        assert stats["worker_type"] == "TelemetryDownloadWorker"
        assert stats["processed_count"] == 10
        assert stats["error_count"] == 2
        assert stats["success_rate"] == 10 / 12
        assert stats["data_path"] == worker.data_path

    def test_get_stats_zero_division(self, worker):
        """Should handle zero division in success rate"""
        stats = worker.get_stats()
        assert stats["success_rate"] == 0

    @patch('requests.get')
    @patch('tempfile.mkstemp')
    def test_download_telemetry_success_not_gzipped(
        self, mock_mkstemp, mock_get, worker, tmp_path
    ):
        """Should download and compress non-gzipped file"""
        # Setup mock temp file
        tmp_file = tmp_path / "temp.json"
        mock_mkstemp.return_value = (os.open(str(tmp_file), os.O_CREAT | os.O_RDWR), str(tmp_file))

        # Setup mock response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b'{"test": "data"}']
        mock_get.return_value = mock_response

        # Execute
        result = worker.download_telemetry(
            "https://telemetry.pubg.com/match.json",
            "match-123"
        )

        # Verify
        assert "file_path" in result
        assert "size_mb" in result
        assert os.path.exists(result["file_path"])
        assert result["file_path"].endswith("raw.json.gz")

        # Verify it's gzipped
        assert is_gzipped(result["file_path"])

    @patch('requests.get')
    @patch('tempfile.mkstemp')
    def test_download_telemetry_already_gzipped(
        self, mock_mkstemp, mock_get, worker, tmp_path
    ):
        """Should handle already-gzipped files"""
        # Create a real gzipped temp file
        tmp_file = tmp_path / "temp.json.gz"
        with gzip.open(tmp_file, 'wb') as f:
            f.write(b'{"test": "data"}')

        mock_mkstemp.return_value = (os.open(str(tmp_file), os.O_RDWR), str(tmp_file))

        # Setup mock response (returns gzipped data)
        mock_response = Mock()
        with open(tmp_file, 'rb') as f:
            gzipped_data = f.read()
        mock_response.iter_content.return_value = [gzipped_data]
        mock_get.return_value = mock_response

        # Execute
        result = worker.download_telemetry(
            "https://telemetry.pubg.com/match.json.gz",
            "match-123"
        )

        # Verify
        assert os.path.exists(result["file_path"])
        assert is_gzipped(result["file_path"])

    @patch('requests.get')
    def test_download_telemetry_retry_on_failure(self, mock_get, worker):
        """Should retry on download failure"""
        # First two attempts fail, third succeeds
        mock_get.side_effect = [
            Exception("Connection timeout"),
            Exception("Connection timeout"),
            Mock(iter_content=lambda chunk_size: [b'{"test": "data"}'])
        ]

        # Execute
        result = worker.download_telemetry(
            "https://telemetry.pubg.com/match.json",
            "match-123"
        )

        # Verify - should have tried 3 times
        assert mock_get.call_count == 3
        assert os.path.exists(result["file_path"])

    @patch('requests.get')
    def test_download_telemetry_max_retries_exceeded(self, mock_get, worker):
        """Should raise exception after max retries"""
        mock_get.side_effect = Exception("Connection timeout")

        # Execute - should raise after 3 attempts
        with pytest.raises(Exception) as exc_info:
            worker.download_telemetry(
                "https://telemetry.pubg.com/match.json",
                "match-123"
            )

        assert "Failed to download telemetry after 3 attempts" in str(exc_info.value)
        assert mock_get.call_count == 3

    @patch('requests.get')
    @patch('tempfile.mkstemp')
    def test_download_telemetry_empty_file(self, mock_mkstemp, mock_get, worker, tmp_path):
        """Should fail if downloaded file is empty"""
        tmp_file = tmp_path / "temp.json"
        # Create the file first to avoid file descriptor issues
        tmp_file.touch()
        mock_mkstemp.return_value = (os.open(str(tmp_file), os.O_RDWR), str(tmp_file))

        # Mock response with empty data
        mock_response = Mock()
        mock_response.iter_content.return_value = []
        mock_get.return_value = mock_response

        # Execute - should fail
        with pytest.raises(Exception) as exc_info:
            worker.download_telemetry(
                "https://telemetry.pubg.com/match.json",
                "match-123"
            )

        # Just check that it failed after retries
        assert "3 attempts" in str(exc_info.value)

    def test_process_message_already_exists(self, worker, mock_rabbitmq_publisher):
        """Should handle existing telemetry (idempotency)"""
        # Create existing file
        match_id = "match-123"
        match_dir = os.path.join(worker.data_path, f"matchID={match_id}")
        os.makedirs(match_dir, exist_ok=True)
        file_path = os.path.join(match_dir, "raw.json.gz")
        with gzip.open(file_path, 'wb') as f:
            f.write(b'{"test": "data"}')

        mock_rabbitmq_publisher.publish_message.return_value = True

        # Execute
        result = worker.process_message({
            "match_id": match_id,
            "telemetry_url": "https://telemetry.pubg.com/match.json",
            "map_name": "Erangel",
            "game_mode": "squad-fpp"
        })

        # Verify
        assert result["success"] is True
        assert result.get("reason") == "already_exists"
        assert worker.processed_count == 1
        # Should still publish to processing queue
        mock_rabbitmq_publisher.publish_message.assert_called_once()

    @patch('requests.get')
    @patch('tempfile.mkstemp')
    def test_process_message_success(
        self, mock_mkstemp, mock_get, worker, mock_rabbitmq_publisher, tmp_path
    ):
        """Should successfully download and publish"""
        # Setup mock temp file
        tmp_file = tmp_path / "temp.json"
        mock_mkstemp.return_value = (os.open(str(tmp_file), os.O_CREAT | os.O_RDWR), str(tmp_file))

        # Setup mock response
        mock_response = Mock()
        mock_response.iter_content.return_value = [b'{"test": "data"}']
        mock_get.return_value = mock_response

        mock_rabbitmq_publisher.publish_message.return_value = True

        # Execute
        result = worker.process_message({
            "match_id": "match-123",
            "telemetry_url": "https://telemetry.pubg.com/match.json",
            "map_name": "Erangel",
            "game_mode": "squad-fpp"
        })

        # Verify
        assert result["success"] is True
        assert worker.processed_count == 1
        assert worker.error_count == 0

        # Verify file was created
        file_path = worker._get_file_path("match-123")
        assert os.path.exists(file_path)

        # Verify publish was called
        mock_rabbitmq_publisher.publish_message.assert_called_once()
        call_args = mock_rabbitmq_publisher.publish_message.call_args
        assert call_args[0][:2] == ("match", "processing")
        message = call_args[0][2]
        assert message["match_id"] == "match-123"

    @patch('requests.get')
    def test_process_message_publish_failure(self, mock_get, worker, mock_rabbitmq_publisher, tmp_path):
        """Should fail if publishing fails"""
        # Setup successful download
        with patch('tempfile.mkstemp') as mock_mkstemp:
            tmp_file = tmp_path / "temp.json"
            mock_mkstemp.return_value = (os.open(str(tmp_file), os.O_CREAT | os.O_RDWR), str(tmp_file))

            mock_response = Mock()
            mock_response.iter_content.return_value = [b'{"test": "data"}']
            mock_get.return_value = mock_response

            # Publish fails
            mock_rabbitmq_publisher.publish_message.return_value = False

            # Execute
            result = worker.process_message({
                "match_id": "match-123",
                "telemetry_url": "https://telemetry.pubg.com/match.json"
            })

            # Verify
            assert result["success"] is False
            assert "publish" in result["error"].lower()
            assert worker.error_count == 1

    @patch('requests.get')
    def test_process_message_download_exception(self, mock_get, worker):
        """Should handle download exceptions"""
        mock_get.side_effect = Exception("Network error")

        result = worker.process_message({
            "match_id": "match-123",
            "telemetry_url": "https://telemetry.pubg.com/match.json"
        })

        assert result["success"] is False
        assert "Network error" in result["error"]
        assert worker.error_count == 1

    def test_publish_processing_message(self, worker, mock_rabbitmq_publisher):
        """Should publish correct message format"""
        mock_rabbitmq_publisher.publish_message.return_value = True

        original_data = {
            "map_name": "Erangel",
            "game_mode": "squad-fpp",
            "match_datetime": "2024-01-15T14:30:45Z"
        }

        success = worker._publish_processing_message(
            "match-123",
            original_data,
            "/path/to/file.json.gz",
            5.5
        )

        assert success is True
        mock_rabbitmq_publisher.publish_message.assert_called_once()

        call_args = mock_rabbitmq_publisher.publish_message.call_args
        assert call_args[0][:2] == ("match", "processing")

        message = call_args[0][2]
        assert message["match_id"] == "match-123"
        assert message["file_path"] == "/path/to/file.json.gz"
        assert message["file_size_mb"] == 5.5
        assert message["map_name"] == "Erangel"
        assert message["game_mode"] == "squad-fpp"
        assert message["worker_id"] == "test-worker-001"
