import threading
import uuid
import zoneinfo

import pghistory
from django.conf import settings
from django.core.handlers.asgi import ASGIRequest as DjangoASGIRequest
from django.core.handlers.wsgi import WSGIRequest as DjangoWSGIRequest
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin
from ipware import get_client_ip
from pghistory import config

threading_local = threading.local()


# The default meta precedence order
IPWARE_META_PRECEDENCE_ORDER = (
    "X_FORWARDED_FOR",
    "HTTP_X_FORWARDED_FOR",
    "HTTP_CLIENT_IP",
    "HTTP_X_REAL_IP",
    "HTTP_X_FORWARDED",
    "HTTP_X_CLUSTER_CLIENT_IP",
    "HTTP_FORWARDED_FOR",
    "HTTP_FORWARDED",
    "HTTP_CF_CONNECTING_IP",
    "X-CLIENT-IP",
    "X-REAL-IP",
    "X-CLUSTER-CLIENT-IP",
    "X_FORWARDED",
    "FORWARDED_FOR",
    "CF-CONNECTING-IP",
    "TRUE-CLIENT-IP",
    "FASTLY-CLIENT-IP",
    "FORWARDED",
    "CLIENT-IP",
    "REMOTE_ADDR",
)


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


class DjangoRequest:
    """
    Although Django's auth middleware sets the user in middleware,
    apps like django-rest-framework set the user in the view layer.
    This creates issues for pghistory tracking since the context needs
    to be set before DB operations happen.

    This special WSGIRequest updates pghistory context when
    the request.user attribute is updated.
    """

    def __setattr__(self, attr, value):
        if attr == "user":
            pghistory.context(user=value.pk if value and hasattr(value, "pk") else None)

        return super().__setattr__(attr, value)


class WSGIRequest(DjangoRequest, DjangoWSGIRequest):
    pass


class ASGIRequest(DjangoRequest, DjangoASGIRequest):
    pass


def HistoryMiddleware(get_response):
    def middleware(request):
        if request.method in config.middleware_methods():
            user = (
                request.user.pk
                if hasattr(request, "user") and hasattr(request.user, "pk")
                else None
            )
            profile = (
                request.user.current_profile.pk
                if hasattr(request.user, "current_profile")
                and hasattr(request.user.current_profile, "pk")
                else None
            )
            client_ip, is_routable = get_client_ip(
                request, request_header_order=IPWARE_META_PRECEDENCE_ORDER
            )

            with pghistory.context(
                user=user,
                profile=profile,
                url=request.path,
                ip_address=client_ip,
                is_ip_routable=is_routable,
            ):
                if isinstance(request, DjangoWSGIRequest):  # pragma: no branch
                    request.__class__ = WSGIRequest
                elif isinstance(request, DjangoASGIRequest):  # pragma: no branch
                    request.__class__ = ASGIRequest

                return get_response(request)
        else:
            return get_response(request)

    return middleware
