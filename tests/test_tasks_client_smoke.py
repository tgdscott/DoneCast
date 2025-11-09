"""Smoke test for tasks_client dispatch system.

This test verifies that task dispatch routes through tasks_client.enqueue_http_task()
and produces the expected log events.
"""
import logging
import os
from unittest.mock import patch

import pytest

from infrastructure.tasks_client import enqueue_http_task


class LogCaptureHandler(logging.Handler):
    """Capture log records for testing."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def has_event(self, event_name: str) -> bool:
        """Check if a log event with the given name was recorded."""
        for record in self.records:
            msg = record.getMessage()
            if f"event={event_name}" in msg:
                return True
        return False

    def get_event_records(self, event_name: str) -> list:
        """Get all log records for a given event name."""
        return [
            record
            for record in self.records
            if f"event={event_name}" in record.getMessage()
        ]


@pytest.fixture
def log_capture():
    """Capture logs from tasks.client logger."""
    handler = LogCaptureHandler()
    logger = logging.getLogger("tasks.client")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield handler
    logger.removeHandler(handler)


def test_enqueue_http_task_dry_run(log_capture):
    """Test that TASKS_DRY_RUN mode works and logs correctly."""
    with patch.dict(os.environ, {"TASKS_DRY_RUN": "true", "APP_ENV": "test"}):
        result = enqueue_http_task("/api/tasks/transcribe", {"filename": "test.wav"})

        # Should return a dry-run task id
        assert "name" in result
        assert result["name"].startswith("dry-run-")

        # Should log the dry-run event
        assert log_capture.has_event("tasks.dry_run")
        dry_run_records = log_capture.get_event_records("tasks.dry_run")
        assert len(dry_run_records) > 0
        assert "path=/api/tasks/transcribe" in dry_run_records[0].getMessage()


def test_enqueue_http_task_routes_through_tasks_client(log_capture):
    """Test that enqueue_http_task produces expected log events.

    This test verifies that task dispatch goes through the centralized
    tasks_client system by checking for the expected log events.
    """
    # Set up test environment to use local dispatch
    with patch.dict(
        os.environ,
        {
            "TASKS_DRY_RUN": "false",
            "APP_ENV": "test",
            "TASKS_FORCE_HTTP_LOOPBACK": "false",
        },
        clear=False,
    ):
        # This should trigger local dispatch in test environment
        result = enqueue_http_task("/api/tasks/transcribe", {"filename": "test.wav"})

        # Should return a task id
        assert "name" in result

        # Should log the start event
        assert log_capture.has_event("tasks.enqueue_http_task.start"), (
            f"Expected 'tasks.enqueue_http_task.start' event. "
            f"Captured events: {[r.getMessage() for r in log_capture.records]}"
        )

        # Should log either local dispatch or cloud tasks usage
        has_local = log_capture.has_event("tasks.enqueue_http_task.using_local_dispatch")
        has_cloud = log_capture.has_event("tasks.enqueue_http_task.using_cloud_tasks")
        assert (
            has_local or has_cloud
        ), "Should log either local dispatch or cloud tasks usage"


def test_enqueue_http_task_fails_with_clear_error():
    """Test that enqueue_http_task raises clear errors (no silent fallbacks)."""
    # Set up environment that requires Cloud Tasks but has missing config
    with patch.dict(
        os.environ,
        {
            "TASKS_DRY_RUN": "false",
            "APP_ENV": "production",  # Force Cloud Tasks path
            "GOOGLE_CLOUD_PROJECT": "",  # Missing required config
            "TASKS_LOCATION": "",
            "TASKS_QUEUE": "",
        },
        clear=False,
    ):
        # Should raise a clear error, not silently fall back
        with pytest.raises((ValueError, ImportError, RuntimeError)) as exc_info:
            enqueue_http_task("/api/tasks/transcribe", {"filename": "test.wav"})

        # Error message should be clear
        error_msg = str(exc_info.value)
        assert "Missing" in error_msg or "not installed" in error_msg or "Failed" in error_msg

