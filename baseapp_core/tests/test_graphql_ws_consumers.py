from unittest.mock import AsyncMock, MagicMock, patch

import channels_graphql_ws
import pytest
from django.contrib.auth.models import AnonymousUser

from baseapp_core.graphql.consumers import GraphqlWsJWTAuthenticatedConsumer

# on_connect delegates auth to the shared helper; patch it where the consumer looks it up.
CONSUMER_AUTH = "baseapp_core.graphql.consumers.authenticate_jwt_async"


def _make_consumer(scope=None):
    with patch.object(channels_graphql_ws.GraphqlWsConsumer, "__init__", return_value=None):
        consumer = GraphqlWsJWTAuthenticatedConsumer()
    consumer.scope = {} if scope is None else scope
    return consumer


class TestGraphqlWsJWTAuthenticatedConsumerOnConnect:
    @pytest.mark.asyncio
    async def test_authenticates_valid_user(self):
        consumer = _make_consumer()
        user = MagicMock(is_active=True)

        with patch(CONSUMER_AUTH, new=AsyncMock(return_value=(user, None))):
            await consumer.on_connect({"Authorization": "valid"})

        assert consumer.scope["user"] is user

    @pytest.mark.asyncio
    async def test_anonymous_when_auth_fails(self):
        consumer = _make_consumer()

        with patch(CONSUMER_AUTH, new=AsyncMock(return_value=(None, None))):
            await consumer.on_connect({"Authorization": "expired", "Refresh": "bad"})

        assert isinstance(consumer.scope["user"], AnonymousUser)

    @pytest.mark.asyncio
    async def test_anonymous_when_no_authorization(self):
        consumer = _make_consumer()

        with patch(CONSUMER_AUTH, new=AsyncMock()) as mock_auth:
            await consumer.on_connect({})

        assert isinstance(consumer.scope["user"], AnonymousUser)
        mock_auth.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_anonymous_when_user_inactive(self):
        consumer = _make_consumer()
        user = MagicMock(is_active=False)

        with patch(CONSUMER_AUTH, new=AsyncMock(return_value=(user, None))):
            await consumer.on_connect({"Authorization": "valid"})

        assert isinstance(consumer.scope["user"], AnonymousUser)

    @pytest.mark.asyncio
    async def test_skips_when_already_authenticated(self):
        sentinel = MagicMock()
        consumer = _make_consumer(scope={"user": sentinel})

        with patch(CONSUMER_AUTH, new=AsyncMock()) as mock_auth:
            await consumer.on_connect({"Authorization": "valid"})

        assert consumer.scope["user"] is sentinel
        mock_auth.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_passes_access_and_refresh_to_authenticator(self):
        consumer = _make_consumer()
        user = MagicMock(is_active=True)

        with patch(CONSUMER_AUTH, new=AsyncMock(return_value=(user, None))) as mock_auth:
            await consumer.on_connect({"Authorization": "access", "Refresh": "refresh"})

        mock_auth.assert_awaited_once_with("access", "refresh")

    @pytest.mark.asyncio
    async def test_ignores_unknown_current_profile(self):
        consumer = _make_consumer()
        user = MagicMock(is_active=True)

        with (
            patch(CONSUMER_AUTH, new=AsyncMock(return_value=(user, None))),
            patch("baseapp_core.graphql.consumers.get_pk_from_relay_id", return_value=None),
        ):
            await consumer.on_connect({"Authorization": "valid", "Current-Profile": "relay-id"})

        assert consumer.scope["user"] is user

    @pytest.mark.asyncio
    async def test_attaches_current_profile_when_permitted(self):
        consumer = _make_consumer()
        profile = MagicMock()
        user = MagicMock(is_active=True)
        user.has_perm = MagicMock(return_value=True)

        with (
            patch(CONSUMER_AUTH, new=AsyncMock(return_value=(user, None))),
            patch("baseapp_core.graphql.consumers.get_pk_from_relay_id", return_value="42"),
            patch("baseapp_core.graphql.consumers.Profile") as profile_model,
        ):
            profile_model.objects.filter.return_value.first.return_value = profile
            await consumer.on_connect({"Authorization": "valid", "Current-Profile": "relay-id"})

        assert consumer.scope["user"] is user
        assert user.current_profile is profile

    @pytest.mark.asyncio
    async def test_does_not_attach_current_profile_without_permission(self):
        consumer = _make_consumer()
        profile = MagicMock()
        user = MagicMock(is_active=True)
        user.has_perm = MagicMock(return_value=False)

        with (
            patch(CONSUMER_AUTH, new=AsyncMock(return_value=(user, None))),
            patch("baseapp_core.graphql.consumers.get_pk_from_relay_id", return_value="42"),
            patch("baseapp_core.graphql.consumers.Profile") as profile_model,
        ):
            profile_model.objects.filter.return_value.first.return_value = profile
            await consumer.on_connect({"Authorization": "valid", "Current-Profile": "relay-id"})

        assert consumer.scope["user"] is user
        assert user.current_profile is not profile
