from unittest.mock import patch

import pytest
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

import baseapp_api_key.tests.factories as f
from baseapp_api_key.graphql.consumers import GraphqlWsAPIKeyAuthenticatedConsumer
from baseapp_api_key.models import APIKey

pytestmark = pytest.mark.django_db(transaction=True)


def _make_consumer() -> GraphqlWsAPIKeyAuthenticatedConsumer:
    consumer = GraphqlWsAPIKeyAuthenticatedConsumer.__new__(GraphqlWsAPIKeyAuthenticatedConsumer)
    consumer.scope = {}
    return consumer


@pytest.mark.asyncio
async def test_on_connect_sets_anonymous_user_when_header_missing() -> None:
    consumer = _make_consumer()

    await consumer.on_connect({})

    assert isinstance(consumer.scope["user"], AnonymousUser)


@pytest.mark.asyncio
async def test_on_connect_sets_anonymous_user_when_key_not_found() -> None:
    consumer = _make_consumer()

    await consumer.on_connect({"HTTP_API_KEY": "BA-nonexistent-key"})

    assert isinstance(consumer.scope["user"], AnonymousUser)


@pytest.mark.asyncio
async def test_on_connect_sets_anonymous_user_when_key_is_expired() -> None:
    api_key = await database_sync_to_async(f.APIKeyFactory)(
        expiry_date=timezone.now() - timezone.timedelta(minutes=1)
    )
    unencrypted = await database_sync_to_async(APIKey.objects.decrypt)(
        encrypted_value=api_key.encrypted_api_key
    )
    consumer = _make_consumer()

    await consumer.on_connect({"HTTP_API_KEY": unencrypted})

    assert isinstance(consumer.scope["user"], AnonymousUser)


@pytest.mark.asyncio
async def test_on_connect_sets_user_when_key_is_valid() -> None:
    api_key = await database_sync_to_async(f.APIKeyFactory)()
    unencrypted = await database_sync_to_async(APIKey.objects.decrypt)(
        encrypted_value=api_key.encrypted_api_key
    )
    user = await database_sync_to_async(lambda: api_key.user)()
    consumer = _make_consumer()

    await consumer.on_connect({"HTTP_API_KEY": unencrypted})

    assert consumer.scope["user"] == user


@pytest.mark.asyncio
async def test_on_connect_skips_auth_when_user_already_in_scope() -> None:
    sentinel = object()
    consumer = _make_consumer()
    consumer.scope["user"] = sentinel

    with patch.object(GraphqlWsAPIKeyAuthenticatedConsumer, "APIKeyModel") as mock_model:
        await consumer.on_connect({"HTTP_API_KEY": "BA-should-not-be-checked"})

    mock_model.objects.encrypt.assert_not_called()
    assert consumer.scope["user"] is sentinel
