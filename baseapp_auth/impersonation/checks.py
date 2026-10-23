from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.checks import Tags, Warning, register
from django.utils.module_loading import import_string

from . import conf

MIDDLEWARE = "baseapp_auth.impersonation.middleware.ImpersonationMiddleware"
GRAPHENE_MIDDLEWARE = (
    "baseapp_auth.impersonation.graphql.middleware.ImpersonationReadOnlyMiddleware"
)
PERMISSIONS_BACKEND = "baseapp_auth.impersonation.permissions.ImpersonationPermissionsBackend"


@register(Tags.security)
def check_impersonation_wiring(app_configs: Any = None, **kwargs: Any) -> list[Warning]:
    """Warn about missing wiring that would let a session skip its checks."""
    warnings = []

    if MIDDLEWARE not in settings.MIDDLEWARE:
        warnings.append(
            Warning(
                "ImpersonationMiddleware is not in MIDDLEWARE, so ended sessions are not "
                "refused, read-only sessions can write over REST, and REST writes are not "
                "recorded.",
                hint=f'Add "{MIDDLEWARE}" to MIDDLEWARE.',
                id="baseapp_impersonation.W001",
            )
        )

    graphene_middleware = getattr(settings, "GRAPHENE", {}).get("MIDDLEWARE", ())
    if apps.is_installed("graphene_django") and GRAPHENE_MIDDLEWARE not in graphene_middleware:
        warnings.append(
            Warning(
                "ImpersonationReadOnlyMiddleware is not in GRAPHENE['MIDDLEWARE'], so "
                "read-only sessions can run mutations and mutations are not recorded.",
                hint=f'Add "{GRAPHENE_MIDDLEWARE}" to GRAPHENE["MIDDLEWARE"].',
                id="baseapp_impersonation.W002",
            )
        )

    refresh_serializer = getattr(settings, "SIMPLE_JWT", {}).get("TOKEN_REFRESH_SERIALIZER")
    if refresh_serializer:
        from .serializers import ImpersonationRefreshSerializerMixin

        try:
            serializer_class = import_string(refresh_serializer)
        except ImportError:
            serializer_class = None
        if serializer_class is not None and not issubclass(
            serializer_class, ImpersonationRefreshSerializerMixin
        ):
            warnings.append(
                Warning(
                    "SIMPLE_JWT['TOKEN_REFRESH_SERIALIZER'] does not use "
                    "ImpersonationRefreshSerializerMixin, so tokens of an ended session can "
                    "still be refreshed (requests made with them are refused).",
                    hint="Use baseapp_auth.impersonation.serializers."
                    "ImpersonationJwtRefreshSerializer, or mix "
                    "ImpersonationRefreshSerializerMixin into your serializer.",
                    id="baseapp_impersonation.W003",
                )
            )

    backends = list(getattr(settings, "AUTHENTICATION_BACKENDS", ()))
    if conf.get_denied_permissions() and (not backends or backends[0] != PERMISSIONS_BACKEND):
        warnings.append(
            Warning(
                "BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS is set but "
                "ImpersonationPermissionsBackend is not the first authentication backend, "
                "so an earlier backend can still grant those permissions.",
                hint=f'Put "{PERMISSIONS_BACKEND}" first in AUTHENTICATION_BACKENDS.',
                id="baseapp_impersonation.W004",
            )
        )

    return warnings


PROCESS_LOCAL_CACHES = ("django.core.cache.backends.locmem.LocMemCache",)


@register(Tags.caches, deploy=True)
def check_impersonation_cache(app_configs: Any = None, **kwargs: Any) -> list[Warning]:
    """
    Warn when sessions are cached per process: ending a session then reaches only the
    process that ended it, and the others accept its tokens until their copy times out.
    """
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if backend not in PROCESS_LOCAL_CACHES or conf.get_cache_timeout() <= 0:
        return []
    return [
        Warning(
            f"Impersonation sessions are cached in {backend.rsplit('.', 1)[-1]}, which is not "
            "shared between processes, so other processes accept an ended session's tokens "
            "for up to BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT seconds.",
            hint="Use a shared cache (e.g. Redis) as the default cache, or set "
            "BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT = 0 to read sessions from the database "
            "on every request.",
            id="baseapp_impersonation.W005",
        )
    ]
