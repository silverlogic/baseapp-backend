import logging
from datetime import timezone
from unittest.mock import patch

import pytest


class TestBaseJSONFormatter:
    @pytest.fixture
    def formatter(self):
        from baseapp_core.logging import BaseJSONFormatter

        return BaseJSONFormatter()

    def _make_record(self, message="test message", name="test.logger", level=logging.INFO):
        return logging.LogRecord(name, level, "", 0, message, None, None)

    def test_json_record_includes_message(self, formatter):
        record = self._make_record("hello world")
        result = formatter.json_record("hello world", {}, record)
        assert result["message"] == "hello world"

    def test_json_record_timestamp_is_utc(self, formatter):
        record = self._make_record()
        result = formatter.json_record("msg", {}, record)
        assert result["@timestamp"].tzinfo is timezone.utc

    def test_json_record_includes_log_level(self, formatter):
        record = self._make_record(level=logging.WARNING)
        result = formatter.json_record("msg", {}, record)
        assert result["log.level"] == "WARNING"

    def test_json_record_includes_logger_name(self, formatter):
        record = self._make_record(name="myapp.module")
        result = formatter.json_record("msg", {}, record)
        assert result["log.logger"] == "myapp.module"

    def test_json_record_merges_request_trace(self, formatter):
        from baseapp_core.middleware import threading_local

        threading_local.request_trace = {"x-trace-id": "abc123"}
        try:
            record = self._make_record()
            result = formatter.json_record("msg", {}, record)
            assert result["x-trace-id"] == "abc123"
        finally:
            del threading_local.request_trace

    def test_json_record_no_request_trace_when_absent(self, formatter):
        from baseapp_core import middleware

        if hasattr(middleware.threading_local, "request_trace"):
            del middleware.threading_local.request_trace
        record = self._make_record()
        result = formatter.json_record("msg", {}, record)
        assert "x-trace-id" not in result

    def test_json_record_includes_sentry_release(self, formatter):
        record = self._make_record()
        with patch("baseapp_core.logging.settings") as mock_settings:
            mock_settings.SENTRY_RELEASE = "v2.0.0"
            result = formatter.json_record("msg", {}, record)
        assert result["service.version"] == "v2.0.0"

    def test_json_record_no_sentry_release_when_absent(self, formatter):
        record = self._make_record()
        with patch("baseapp_core.logging.settings") as mock_settings:
            mock_settings.SENTRY_RELEASE = None
            result = formatter.json_record("msg", {}, record)
        assert "service.version" not in result

    def test_json_record_includes_celery_trace_id(self, formatter):
        record = self._make_record()
        record.data = {"id": "celery-task-456"}
        result = formatter.json_record("msg", {}, record)
        assert result["trace.id"] == "celery-task-456"

    def test_json_record_no_celery_data_when_absent(self, formatter):
        record = self._make_record()
        result = formatter.json_record("msg", {}, record)
        assert "trace.id" not in result

    def test_to_json_removes_request_key(self, formatter):
        import json

        json_str = formatter.to_json({"request": "some_request_object", "message": "hello"})
        data = json.loads(json_str)
        assert "request" not in data
        assert data["message"] == "hello"

    def test_to_json_preserves_other_keys(self, formatter):
        import json

        json_str = formatter.to_json({"level": "INFO", "message": "test"})
        data = json.loads(json_str)
        assert data["level"] == "INFO"
