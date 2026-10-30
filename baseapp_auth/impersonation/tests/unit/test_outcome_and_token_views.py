from types import SimpleNamespace

import pytest
from django.urls import resolve
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from ...services import is_token_view, mutation_succeeded


@pytest.mark.parametrize(
    "result, expected",
    [
        (SimpleNamespace(errors=None), True),
        (SimpleNamespace(errors=[]), True),
        (SimpleNamespace(errors=[{"field": "x", "messages": ["bad"]}]), False),
        (SimpleNamespace(), True),
    ],
)
def test_mutation_succeeded(result, expected) -> None:
    assert mutation_succeeded(result) is expected


def test_mutation_outcome_unknown_while_awaitable() -> None:
    async def pending() -> None:
        return None

    coroutine = pending()
    assert mutation_succeeded(coroutine) is None
    coroutine.close()


def test_token_views() -> None:
    assert is_token_view(TokenRefreshView.as_view(), "POST")
    assert not is_token_view(TokenObtainPairView.as_view(), "POST")
    assert not is_token_view(lambda request: None, "POST")


def test_token_viewset_actions() -> None:
    # BaseApp's JWTAuthViewSet serves login and refresh; only refresh is a token request.
    assert is_token_view(resolve("/v1/auth/jwt/refresh").func, "POST")
    assert not is_token_view(resolve("/v1/auth/jwt/login").func, "POST")
