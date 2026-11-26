from unittest.mock import AsyncMock, patch

import pytest
from channels.db import database_sync_to_async
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

import baseapp_auth.tests.helpers as h
from baseapp_auth.graphql.consumers import (
    GraphqlWsAllAuthJWTAuthenticatedConsumer,
    get_allauth_jwt_user,
)

UserFactory = h.get_user_factory()

pytestmark = pytest.mark.django_db(transaction=True)


@database_sync_to_async
def _create_access_token(user):
    from allauth.headless.tokens.strategies.jwt import JWTTokenStrategy

    rf = RequestFactory()
    request = rf.get("/")
    request.user = user

    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()

    strategy = JWTTokenStrategy()
    return strategy.create_access_token(request)


@pytest.mark.asyncio
async def test_allauth_consumer_authenticates_allauth_access_token(django_user_client) -> None:
    consumer = GraphqlWsAllAuthJWTAuthenticatedConsumer()

    access_token = await _create_access_token(django_user_client.user)

    user = await consumer.authenticate({"Authorization": access_token})

    assert user == django_user_client.user


@pytest.mark.asyncio
async def test_allauth_consumer_falls_back_to_simplejwt(django_user_client) -> None:
    consumer = GraphqlWsAllAuthJWTAuthenticatedConsumer()

    with patch(
        "baseapp_core.graphql.consumers.authenticate_jwt_async",
        new=AsyncMock(return_value=(django_user_client.user, None)),
    ) as mock_simplejwt:
        user = await consumer.authenticate({"Authorization": "simplejwt-token", "Refresh": "r"})

    assert user == django_user_client.user
    mock_simplejwt.assert_awaited_once_with("simplejwt-token", "r")


@pytest.mark.asyncio
async def test_allauth_consumer_rejects_invalid_token() -> None:
    consumer = GraphqlWsAllAuthJWTAuthenticatedConsumer()

    user = await consumer.authenticate({"Authorization": "invalid_token"})

    assert user is None


@pytest.mark.asyncio
async def test_get_allauth_jwt_user_logs_and_returns_none_on_unexpected_error() -> None:
    with (
        patch(
            "allauth.headless.tokens.strategies.jwt.internal.validate_access_token",
            side_effect=RuntimeError("boom"),
        ),
        patch("baseapp_auth.graphql.consumers.logger.exception") as mock_log,
    ):
        user = await get_allauth_jwt_user("any")

    assert user is None
    mock_log.assert_called_once()


@pytest.mark.asyncio
async def test_allauth_consumer_on_connect_sets_scope_user(django_user_client) -> None:
    consumer = GraphqlWsAllAuthJWTAuthenticatedConsumer()
    consumer.scope = {}

    access_token = await _create_access_token(django_user_client.user)
    await consumer.on_connect({"Authorization": access_token})

    assert consumer.scope["user"] == django_user_client.user
