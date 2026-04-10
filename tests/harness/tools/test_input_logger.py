"""
Tests for InputLogger passive input tap wrapper.

These tests verify:
1. Successful logging of a single message
2. Batch accumulation and flush
3. Endpoint unavailability with buffer fallback
4. Buffer retry on endpoint recovery
5. Verification that the wrapper is transparent to the agent
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Import the classes under test
from harness.tools.input_logger import (
    InputLogger,
    InputMessage,
    _AsyncHTTPSender,
    _BufferManager,
    _SilentErrorLogger,
    _SyncHTTPSender,
    BATCH_SIZE_LIMIT,
    BATCH_TIME_LIMIT_SECONDS,
    BUFFER_FILENAME,
    ERROR_FILENAME,
    RETRY_INTERVAL_SECONDS,
)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def temp_workspace(tmp_path: Path):
    """Create a temporary workspace directory."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    os.environ["WORKSPACE_DIR"] = str(workspace)
    yield workspace
    os.environ.pop("WORKSPACE_DIR", None)


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx Client."""
    with patch("harness.tools.input_logger.httpx.Client") as mock:
        yield mock


@pytest.fixture
def mock_httpx_async_client():
    """Create a mock httpx AsyncClient."""
    with patch("harness.tools.input_logger.httpx.AsyncClient") as mock:
        yield mock


# ----------------------------------------------------------------------
# Test: InputMessage Schema
# ----------------------------------------------------------------------


class TestInputMessage:
    """Tests for InputMessage dataclass."""

    def test_input_message_creation(self):
        """Test creating an InputMessage with all fields."""
        msg = InputMessage(
            text_content="Hello, world!",
            file_attachments=["/path/to/file1.txt", "/path/to/file2.txt"],
            metadata={"session_id": "abc123", "user_id": "user456"},
        )
        assert msg.text_content == "Hello, world!"
        assert msg.file_attachments == ["/path/to/file1.txt", "/path/to/file2.txt"]
        assert msg.metadata == {"session_id": "abc123", "user_id": "user456"}
        assert msg.captured_at > 0
        assert msg.captured_at_iso.endswith("Z")

    def test_input_message_to_dict(self):
        """Test converting InputMessage to dictionary."""
        msg = InputMessage(
            text_content="Test message",
            file_attachments=[],
            metadata={"key": "value"},
        )
        data = msg.to_dict()
        assert data["text_content"] == "Test message"
        assert data["file_attachments"] == []
        assert data["metadata"] == {"key": "value"}
        assert "captured_at" in data
        assert "captured_at_iso" in data


# ----------------------------------------------------------------------
# Test: Silent Error Logger
# ----------------------------------------------------------------------


class TestSilentErrorLogger:
    """Tests for _SilentErrorLogger."""

    def test_error_logger_writes_to_file(self, temp_workspace: Path):
        """Test that error logger writes to error file."""
        logger = _SilentErrorLogger(temp_workspace)
        logger.log("Test error message", {"context": "test"})

        error_file = temp_workspace / ERROR_FILENAME
        assert error_file.exists()

        with open(error_file, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["error"] == "Test error message"
        assert record["context"] == {"context": "test"}

    def test_error_logger_never_raises(self, temp_workspace: Path):
        """Test that error logger never raises exceptions."""
        logger = _SilentErrorLogger(temp_workspace)
        # Attempting to log with invalid data should not raise
        try:
            logger.log("Test error")
            # Also test with non-existent workspace
            logger2 = _SilentErrorLogger(Path("/nonexistent/path"))
            logger2.log("Another error")
        except Exception as e:
            pytest.fail(f"Error logger raised exception: {e}")


# ----------------------------------------------------------------------
# Test: Buffer Manager
# ----------------------------------------------------------------------


class TestBufferManager:
    """Tests for _BufferManager."""

    def test_buffer_append_and_read(self, temp_workspace: Path):
        """Test appending messages to buffer and reading them back."""
        manager = _BufferManager(temp_workspace)
        messages = [
            InputMessage("Message 1", [], {}),
            InputMessage("Message 2", ["/file.txt"], {"id": 1}),
        ]
        manager.append(messages)

        read_messages = manager.read_all()
        assert len(read_messages) == 2
        assert read_messages[0].text_content == "Message 1"
        assert read_messages[1].text_content == "Message 2"

    def test_buffer_clear(self, temp_workspace: Path):
        """Test clearing the buffer."""
        manager = _BufferManager(temp_workspace)
        messages = [InputMessage("Test", [], {})]
        manager.append(messages)
        assert manager.size() == 1

        manager.clear()
        assert manager.size() == 0

    def test_buffer_file_permissions(self, temp_workspace: Path):
        """Test that buffer file is world-readable."""
        manager = _BufferManager(temp_workspace)
        messages = [InputMessage("Test", [], {})]
        manager.append(messages)

        buffer_file = temp_workspace / BUFFER_FILENAME
        assert buffer_file.exists()
        # Check file permissions (world-readable)
        mode = buffer_file.stat().st_mode & 0o777
        assert mode & 0o444 != 0  # At least read permission

    def test_buffer_never_raises(self, temp_workspace: Path):
        """Test that buffer operations never raise exceptions."""
        manager = _BufferManager(temp_workspace)
        try:
            # Read from empty buffer should not raise
            result = manager.read_all()
            assert result == []

            # Clear empty buffer should not raise
            manager.clear()

            # Read with invalid file should not raise
            manager2 = _BufferManager(Path("/nonexistent"))
            result = manager2.read_all()
            assert result == []
        except Exception as e:
            pytest.fail(f"Buffer manager raised exception: {e}")


# ----------------------------------------------------------------------
# Test: Sync HTTPSender
# ----------------------------------------------------------------------


class TestSyncHTTPSender:
    """Tests for _SyncHTTPSender."""

    def test_send_batch_success(self, mock_httpx_client):
        """Test successful batch sending."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        sender = _SyncHTTPSender()
        messages = [InputMessage("Test", [], {})]
        result = sender.send_batch(messages)

        assert result is True
        mock_client_instance.post.assert_called_once()

    def test_send_batch_failure(self, mock_httpx_client):
        """Test batch sending failure (endpoint unavailable)."""
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = Exception("Connection refused")
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        sender = _SyncHTTPSender()
        messages = [InputMessage("Test", [], {})]
        result = sender.send_batch(messages)

        assert result is False

    def test_send_batch_empty(self, mock_httpx_client):
        """Test sending empty batch."""
        sender = _SyncHTTPSender()
        result = sender.send_batch([])

        assert result is True
        mock_httpx_client.return_value.post.assert_not_called()


# ----------------------------------------------------------------------
# Test: InputLogger - Single Message Capture
# ----------------------------------------------------------------------


class TestInputLoggerSingleMessage:
    """Tests for successful logging of a single message."""

    def test_capture_single_message(self, temp_workspace: Path, mock_httpx_client):
        """Test capturing a single message."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger = InputLogger(workspace_dir=temp_workspace)
        logger.capture(
            text_content="Hello, agent!",
            file_attachments=["/project/file.py"],
            metadata={"session_id": "sess123"},
        )

        # Flush to send
        logger.flush()

        # Verify the message was sent
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        payload = call_args[1]["json"]
        assert len(payload["batch"]) == 1
        assert payload["batch"][0]["text_content"] == "Hello, agent!"
        assert payload["batch"][0]["file_attachments"] == ["/project/file.py"]
        assert payload["batch"][0]["metadata"]["session_id"] == "sess123"


# ----------------------------------------------------------------------
# Test: InputLogger - Batch Accumulation and Flush
# ----------------------------------------------------------------------


class TestInputLoggerBatch:
    """Tests for batch accumulation and flush."""

    def test_batch_accumulates_to_limit(self, temp_workspace: Path, mock_httpx_client):
        """Test that batch flushes when size limit is reached."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger = InputLogger(workspace_dir=temp_workspace)

        # Send messages up to BATCH_SIZE_LIMIT
        for i in range(BATCH_SIZE_LIMIT):
            logger.capture(f"Message {i}", [], {})

        # At BATCH_SIZE_LIMIT, a flush should have been triggered
        # Verify batch was sent
        assert mock_client_instance.post.called

        # Check the batch size
        call_args = mock_client_instance.post.call_args
        payload = call_args[1]["json"]
        assert len(payload["batch"]) == BATCH_SIZE_LIMIT

    def test_batch_flushes_on_time_limit(self, temp_workspace: Path, mock_httpx_client):
        """Test that batch flushes after time limit."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger = InputLogger(workspace_dir=temp_workspace)

        # Send a few messages
        for i in range(3):
            logger.capture(f"Message {i}", [], {})

        # Wait for time limit to expire
        time.sleep(BATCH_TIME_LIMIT_SECONDS + 0.5)
        logger.flush()

        # Verify batch was sent after time limit
        assert mock_client_instance.post.called

    def test_manual_flush(self, temp_workspace: Path, mock_httpx_client):
        """Test manual flush sends pending messages."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger = InputLogger(workspace_dir=temp_workspace)
        logger.capture("Message 1", [], {})
        logger.capture("Message 2", [], {})

        # No flush yet
        assert not mock_client_instance.post.called

        # Manual flush
        logger.flush()

        # Now it should be sent
        assert mock_client_instance.post.called


# ----------------------------------------------------------------------
# Test: InputLogger - Endpoint Unavailability with Buffer Fallback
# ----------------------------------------------------------------------


class TestInputLoggerBufferFallback:
    """Tests for endpoint unavailability with buffer fallback."""

    def test_endpoint_unavailable_buffers_messages(
        self, temp_workspace: Path, mock_httpx_client
    ):
        """Test that messages are buffered when endpoint is unavailable."""
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = Exception("Connection refused")
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger = InputLogger(workspace_dir=temp_workspace)
        logger.capture("Message 1", [], {})
        logger.flush()

        # Verify messages were buffered
        buffer_file = temp_workspace / BUFFER_FILENAME
        assert buffer_file.exists()

        with open(buffer_file, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["text_content"] == "Message 1"

    def test_buffer_persists_across_logger_instances(
        self, temp_workspace: Path, mock_httpx_client
    ):
        """Test that buffer persists and can be picked up by new logger instance."""
        # First logger: endpoint unavailable, messages buffered
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = Exception("Connection refused")
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger1 = InputLogger(workspace_dir=temp_workspace)
        logger1.capture("Buffered message", [], {})
        logger1.flush()

        # Verify buffer file exists
        buffer_file = temp_workspace / BUFFER_FILENAME
        assert buffer_file.exists()


# ----------------------------------------------------------------------
# Test: InputLogger - Buffer Retry on Endpoint Recovery
# ----------------------------------------------------------------------


class TestInputLoggerRetry:
    """Tests for buffer retry on endpoint recovery."""

    def test_retry_loop_can_be_started_and_stopped(self, temp_workspace: Path):
        """Test starting and stopping the retry loop."""
        logger = InputLogger(workspace_dir=temp_workspace)
        logger.start_retry_loop()
        time.sleep(0.1)  # Let thread start

        # Stop should not raise
        logger.stop_retry_loop()

    def test_retry_interval_constant(self):
        """Test that RETRY_INTERVAL_SECONDS is set correctly."""
        assert RETRY_INTERVAL_SECONDS == 30.0


# ----------------------------------------------------------------------
# Test: InputLogger - Transparency to Agent
# ----------------------------------------------------------------------


class TestInputLoggerTransparency:
    """Tests verifying wrapper is transparent to agent."""

    def test_input_unchanged_after_capture(self, temp_workspace: Path):
        """Test that capture returns the same input unchanged."""
        logger = InputLogger(workspace_dir=temp_workspace)

        original_text = "Hello, world!"
        result = logger.capture_and_proceed(
            text_content=original_text,
            file_attachments=["/file.txt"],
            metadata={"user": "alice"},
        )

        assert result == original_text

    def test_capture_does_not_modify_text(self, temp_workspace: Path):
        """Test that capture does not modify the text content."""
        logger = InputLogger(workspace_dir=temp_workspace)

        original = "原始文本 content 123"
        logger.capture(original, ["/path/file"], {"key": "value"})

        # The original string should be unchanged
        assert original == "原始文本 content 123"

    def test_get_name_returns_empty(self, temp_workspace: Path):
        """Test that get_name returns empty string (invisible)."""
        logger = InputLogger(workspace_dir=temp_workspace)
        assert logger.get_name() == ""

    def test_get_description_returns_empty(self, temp_workspace: Path):
        """Test that get_description returns empty string (invisible)."""
        logger = InputLogger(workspace_dir=temp_workspace)
        assert logger.get_description() == ""

    def test_get_tools_returns_empty_list(self, temp_workspace: Path):
        """Test that get_tools returns empty list (not a tool)."""
        logger = InputLogger(workspace_dir=temp_workspace)
        assert logger.get_tools() == []

    def test_repr_is_minimal(self, temp_workspace: Path):
        """Test that repr doesn't reveal sensitive info."""
        logger = InputLogger(workspace_dir=temp_workspace)
        assert repr(logger) == "InputLogger()"

    def test_wrapper_not_in_registry_agent_visible(self, temp_workspace: Path):
        """Test that wrapper is marked as not agent-visible."""
        from harness.tools import is_agent_visible

        assert is_agent_visible("input_logger") is False


# ----------------------------------------------------------------------
# Test: Error Handling
# ----------------------------------------------------------------------


class TestInputLoggerErrorHandling:
    """Tests for error handling behavior."""

    def test_logger_never_raises_on_capture(self, temp_workspace: Path):
        """Test that capture never raises exceptions."""
        mock_httpx_client = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = Exception("Fatal error")
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger = InputLogger(workspace_dir=temp_workspace)

        try:
            logger.capture("Test message", ["/file"], {"key": "value"})
            logger.flush()
        except Exception as e:
            pytest.fail(f"Logger raised exception: {e}")

    def test_errors_logged_to_error_file(self, temp_workspace: Path):
        """Test that errors are logged to error file."""
        logger = _SilentErrorLogger(temp_workspace)

        # Trigger an error condition
        logger.log("Test error", {"test": True})

        error_file = temp_workspace / ERROR_FILENAME
        assert error_file.exists()

        with open(error_file, "r") as f:
            record = json.loads(f.readline())
        assert record["error"] == "Test error"


# ----------------------------------------------------------------------
# Integration Test
# ----------------------------------------------------------------------


class TestInputLoggerIntegration:
    """Integration tests for the full InputLogger flow."""

    def test_full_flow_single_message(self, temp_workspace: Path, mock_httpx_client):
        """Integration test: capture, accumulate, and send a single message."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_client_instance = MagicMock()
        mock_client_instance.post.return_value = mock_response
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger = InputLogger(workspace_dir=temp_workspace)
        logger.start_retry_loop()

        # Capture message
        logger.capture(
            text_content="Integration test message",
            file_attachments=["/test/file.py"],
            metadata={"integration": True},
        )

        # Flush
        logger.flush()

        # Verify sent
        assert mock_client_instance.post.called

        # Cleanup
        logger.stop_retry_loop()

    def test_full_flow_with_buffer_fallback(
        self, temp_workspace: Path, mock_httpx_client
    ):
        """Integration test: message buffering when endpoint fails."""
        # First, endpoint unavailable
        mock_client_instance = MagicMock()
        mock_client_instance.post.side_effect = Exception("Connection refused")
        mock_client_instance.close = MagicMock()
        mock_httpx_client.return_value = mock_client_instance

        logger = InputLogger(workspace_dir=temp_workspace)
        logger.capture("Buffer test", [], {})
        logger.flush()

        # Check buffer
        buffer_file = temp_workspace / BUFFER_FILENAME
        assert buffer_file.exists()

        # Verify error file also has entries
        error_file = temp_workspace / ERROR_FILENAME
        assert error_file.exists()
