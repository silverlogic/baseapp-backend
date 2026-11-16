import logging
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from baseapp_core.logging import BaseJSONFormatter


class TestBaseJSONFormatter:
    @pytest.fixture
    def formatter(self) -> "BaseJSONFormatter":
        from baseapp_core.logging import BaseJSONFormatter

        return BaseJSONFormatter()

    def _make_record(
        self,
        message="test message",
        name="test.logger",
        level=logging.INFO,
        exc_info=None,
        stack_info=None,
    ) -> logging.LogRecord:
        return logging.LogRecord(name, level, "", 0, message, None, exc_info, sinfo=stack_info)

    def test_json_record_includes_message(self, formatter) -> None:
        record = self._make_record("hello world")
        result = formatter.json_record("hello world", {}, record)
        assert result["message"] == "hello world"

    def test_json_record_timestamp_is_utc(self, formatter) -> None:
        record = self._make_record()
        result = formatter.json_record("msg", {}, record)
        assert isinstance(result["@timestamp"], str)
        assert result["@timestamp"].endswith("+00:00")

    def test_json_record_includes_log_level(self, formatter) -> None:
        record = self._make_record(level=logging.WARNING)
        result = formatter.json_record("msg", {}, record)
        assert result["log.level"] == "WARNING"

    def test_json_record_includes_logger_name(self, formatter) -> None:
        record = self._make_record(name="myapp.module")
        result = formatter.json_record("msg", {}, record)
        assert result["log.logger"] == "myapp.module"

    def test_json_record_merges_request_trace(self, formatter) -> None:
        from baseapp_core.middleware import threading_local

        threading_local.request_trace = {"x-trace-id": "abc123"}
        try:
            record = self._make_record()
            result = formatter.json_record("msg", {}, record)
            assert result["x-trace-id"] == "abc123"
        finally:
            del threading_local.request_trace

    def test_json_record_no_request_trace_when_absent(self, formatter) -> None:
        from baseapp_core import middleware

        if hasattr(middleware.threading_local, "request_trace"):
            del middleware.threading_local.request_trace
        record = self._make_record()
        result = formatter.json_record("msg", {}, record)
        assert "x-trace-id" not in result

    def test_json_record_includes_sentry_release(self, formatter) -> None:
        record = self._make_record()
        with patch("baseapp_core.logging.settings") as mock_settings:
            mock_settings.SENTRY_RELEASE = "v2.0.0"
            result = formatter.json_record("msg", {}, record)
        assert result["service.version"] == "v2.0.0"

    def test_json_record_no_sentry_release_when_absent(self, formatter) -> None:
        record = self._make_record()
        with patch("baseapp_core.logging.settings") as mock_settings:
            mock_settings.SENTRY_RELEASE = None
            result = formatter.json_record("msg", {}, record)
        assert "service.version" not in result

    def test_json_record_includes_celery_trace_id(self, formatter) -> None:
        record = self._make_record()
        record.data = {"id": "celery-task-456"}
        result = formatter.json_record("msg", {}, record)
        assert result["trace.id"] == "celery-task-456"

    def test_json_record_no_celery_data_when_absent(self, formatter) -> None:
        record = self._make_record()
        result = formatter.json_record("msg", {}, record)
        assert "trace.id" not in result

    def test_json_record_includes_exception_traceback(self, formatter) -> None:
        try:
            raise ValueError("boom-xyz")
        except ValueError:
            record = self._make_record(level=logging.ERROR, exc_info=sys.exc_info())
        result = formatter.json_record("msg", {}, record)
        assert "Traceback" in result["error.stack_trace"]
        assert "ValueError: boom-xyz" in result["error.stack_trace"]

    def test_json_record_falls_back_to_exc_text(self, formatter) -> None:
        record = self._make_record(level=logging.ERROR)
        record.exc_text = "Traceback (most recent call last):\n  RuntimeError: cached"
        result = formatter.json_record("msg", {}, record)
        assert result["error.stack_trace"] == record.exc_text

    def test_json_record_no_stack_trace_without_exception(self, formatter) -> None:
        record = self._make_record(level=logging.WARNING)
        result = formatter.json_record("msg", {}, record)
        assert "error.stack_trace" not in result
        assert "error.stack_info" not in result

    def test_json_record_includes_stack_info(self, formatter) -> None:
        record = self._make_record(stack_info="Stack (most recent call last):\n  frame")
        result = formatter.json_record("msg", {}, record)
        assert "frame" in result["error.stack_info"]

    def test_format_with_exception_is_single_line_json(self, formatter) -> None:
        import json

        try:
            raise RuntimeError("multi\nline")
        except RuntimeError:
            record = self._make_record(level=logging.ERROR, exc_info=sys.exc_info())
        rendered = formatter.format(record)
        assert "\n" not in rendered
        data = json.loads(rendered)
        assert data["log.level"] == "ERROR"
        assert "RuntimeError: multi" in data["error.stack_trace"]

    def test_to_json_removes_request_key(self, formatter) -> None:
        import json

        json_str = formatter.to_json({"request": "some_request_object", "message": "hello"})
        data = json.loads(json_str)
        assert "request" not in data
        assert data["message"] == "hello"

    def test_to_json_preserves_other_keys(self, formatter) -> None:
        import json

        json_str = formatter.to_json({"level": "INFO", "message": "test"})
        data = json.loads(json_str)
        assert data["level"] == "INFO"
