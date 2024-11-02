import pghistory
from django.core.handlers.asgi import ASGIRequest as DjangoASGIRequest
from django.core.handlers.wsgi import WSGIRequest as DjangoWSGIRequest
from ipware import get_client_ip
from pghistory import config

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
