import pytest
from django.test import override_settings

from ...checks import (
    GRAPHENE_MIDDLEWARE,
    MIDDLEWARE,
    PERMISSIONS_BACKEND,
    check_impersonation_wiring,
)


def ids(**overrides) -> set[str]:
    with override_settings(**overrides):
        return {warning.id for warning in check_impersonation_wiring()}


def test_testproject_is_fully_wired() -> None:
    assert check_impersonation_wiring() == []


def test_missing_middleware() -> None:
    from django.conf import settings

    middleware = [m for m in settings.MIDDLEWARE if m != MIDDLEWARE]
    assert "baseapp_impersonation.W001" in ids(MIDDLEWARE=middleware)


def test_missing_graphene_middleware() -> None:
    from django.conf import settings

    graphene = {
        **settings.GRAPHENE,
        "MIDDLEWARE": [m for m in settings.GRAPHENE["MIDDLEWARE"] if m != GRAPHENE_MIDDLEWARE],
    }
    assert "baseapp_impersonation.W002" in ids(GRAPHENE=graphene)


def test_refresh_serializer_without_the_mixin() -> None:
    simple_jwt = {
        "TOKEN_REFRESH_SERIALIZER": (
            "baseapp_auth.rest_framework.jwt.serializers.BaseJwtRefreshSerializer"
        )
    }
    assert "baseapp_impersonation.W003" in ids(SIMPLE_JWT=simple_jwt)


@pytest.mark.parametrize(
    "backends, warned",
    [
        (["django.contrib.auth.backends.ModelBackend", PERMISSIONS_BACKEND], True),
        ([PERMISSIONS_BACKEND, "django.contrib.auth.backends.ModelBackend"], False),
    ],
)
def test_denied_permissions_need_the_backend_first(backends, warned) -> None:
    result = ids(
        AUTHENTICATION_BACKENDS=backends,
        BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS=["app.perm"],
    )
    assert ("baseapp_impersonation.W004" in result) is warned
