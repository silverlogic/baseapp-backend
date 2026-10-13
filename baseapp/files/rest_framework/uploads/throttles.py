from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class AnonymousUploadThrottle(SimpleRateThrottle):
    """Rate-limits anonymous upload initiation per client IP (``BASEAPP_FILES_ANONYMOUS_UPLOAD_RATE``)."""

    scope = "baseapp_files_anonymous_upload"

    def get_rate(self) -> str | None:
        return getattr(settings, "BASEAPP_FILES_ANONYMOUS_UPLOAD_RATE", "20/hour")

    def get_cache_key(self, request, view) -> str | None:
        if request.user and request.user.is_authenticated:
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
