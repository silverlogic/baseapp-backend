from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory

import baseapp_auth.tests.helpers as h
from baseapp_auth.graphql.consumers import GraphqlWsAllAuthJWTAuthenticatedConsumer

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
async def test_graphql_ws_allauth_jwt_consumer_get_jwt_user_instance_success(django_user_client):
    consumer = GraphqlWsAllAuthJWTAuthenticatedConsumer()

    access_token = await _create_access_token(django_user_client.user)

    user = await consumer.get_jwt_user_instance(access_token)

    assert user == django_user_client.user


@pytest.mark.asyncio
async def test_graphql_ws_allauth_jwt_consumer_get_jwt_user_instance_invalid_token_logs_and_returns_none():
    consumer = GraphqlWsAllAuthJWTAuthenticatedConsumer()

    with patch("baseapp_auth.graphql.consumers.logging.error") as mock_log_error:
        user = await consumer.get_jwt_user_instance("invalid_token")

    assert user is None
    mock_log_error.assert_called_once()


@pytest.mark.asyncio
async def test_graphql_ws_allauth_jwt_consumer_get_jwt_user_instance_raises_when_not_initialized():
    consumer = GraphqlWsAllAuthJWTAuthenticatedConsumer()
    consumer._auth = None

    with pytest.raises(
        RuntimeError,
        match="The _setup method must be called first",
    ):
        await consumer.get_jwt_user_instance("test_token")
