import threading
import uuid
import zoneinfo
import warnings

from django.conf import settings

from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from baseapp_core.deprecation import RemovedInBaseApp04Warning
from baseapp_activity_log.middleware import HistoryMiddleware as BaseHistoryMiddleware

threading_local = threading.local()


class AdminTimezoneMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Accessing request.user will activate the sessions/auth middleware.  This
        # causes the Vary: Cookie header to be set.  If this happens on an API call
        # it will greatly reduce the effectiveness of http caching (e.g. using varnish).
        # To get around this we make sure we only access the request user if we the URL matches
        # the admin.
        if request.path.startswith("/admin") and request.user.is_superuser:
            timezone.activate(zoneinfo.ZoneInfo(settings.ADMIN_TIME_ZONE))


class ThreadAttachedRequestLocalMiddleware(MiddlewareMixin):
    def __call__(self, request):
        request_trace = {"trace.id": uuid.uuid4()}
        if request.user:
            request_trace["user.id"] = request.user.id
            request_trace["user.email"] = request.user.email
        setattr(threading_local, "request_trace", request_trace)
        response = self.get_response(request)
        setattr(threading_local, "request_trace", None)
        return response


def HistoryMiddleware(get_response):
    warnings.warn(
        "baseapp_core.middleware.HistoryMiddleware is deprecated and will be removed in baseapp-core 0.4.0. Please use baseapp_activity_log.middleware.HistoryMiddleware instead.",
        RemovedInBaseApp04Warning,
        stacklevel=2,
    )
    middleware = BaseHistoryMiddleware(get_response)
    return middleware