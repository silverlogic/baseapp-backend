import pytest
import strawberry
from channels.db import database_sync_to_async
from django.utils import timezone
from strawberry.channels.testing import GraphQLWebsocketCommunicator
from strawberry.types import Info

import baseapp_api_key.tests.factories as f
from baseapp_api_key.models import APIKey
from baseapp_api_key.strawberry.consumers import GraphQLWSAPIKeyConsumer

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


@strawberry.type
class Query:
    @strawberry.field
    def whoami(self, info: Info) -> str | None:
        user = info.context.user
        return user.email if user.is_authenticated else None


application = GraphQLWSAPIKeyConsumer.as_asgi(schema=strawberry.Schema(query=Query))


async def _whoami(params: dict) -> str | None:
    async with GraphQLWebsocketCommunicator(
        application, "/graphql", connection_params=params
    ) as ws:
        async for result in ws.subscribe("{ whoami }"):
            return result.data["whoami"]


async def _unencrypted_key(**factory_kwargs) -> tuple:
    api_key = await database_sync_to_async(f.APIKeyFactory)(**factory_kwargs)
    unencrypted = await database_sync_to_async(APIKey.objects.decrypt)(
        encrypted_value=api_key.encrypted_api_key
    )
    email = await database_sync_to_async(lambda: api_key.user.email)()
    return unencrypted, email


async def test_missing_or_unknown_key_is_anonymous() -> None:
    assert await _whoami({}) is None
    assert await _whoami({"HTTP_API_KEY": "BA-nonexistent-key"}) is None


async def test_expired_key_is_anonymous() -> None:
    unencrypted, _ = await _unencrypted_key(
        expiry_date=timezone.now() - timezone.timedelta(minutes=1)
    )
    assert await _whoami({"HTTP_API_KEY": unencrypted}) is None


async def test_valid_key_authenticates() -> None:
    unencrypted, email = await _unencrypted_key()
    assert await _whoami({"HTTP_API_KEY": unencrypted}) == email
