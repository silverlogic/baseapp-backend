from datetime import datetime
from logging import LogRecord

from django.conf import settings
from django.utils import timezone
from json_log_formatter import JSONFormatter

from .middleware import threading_local


class BaseJSONFormatter(JSONFormatter):
    def json_record(self, message: str, extra: dict, record: LogRecord) -> dict:
        extra["message"] = message
        timestamp = datetime.utcfromtimestamp(record.created)
        extra["@timestamp"] = timezone.make_aware(timestamp)
        extra["log.level"] = record.levelname
        extra["log.logger"] = record.name

        request_trace = getattr(threading_local, "request_trace", None)
        if request_trace:
            extra = {**extra, **request_trace}

        sentry_release = getattr(settings, "SENTRY_RELEASE", None)
        if sentry_release:
            extra["service.version"] = sentry_release
        # celery task adds the data attribute
        celery_data = getattr(record, "data", None)
        if celery_data:
            extra["trace.id"] = celery_data["id"]

        return extra

    def to_json(self, record):
        # Performance increase a lot by removing the request. Otherwise, it
        # tries to parse a very huge json data
        record.pop("request", None)
        return super().to_json(record)
