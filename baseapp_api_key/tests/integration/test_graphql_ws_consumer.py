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

    @strawberry.field
    def current_profile_id(self, info: Info) -> int | None:
        profile = getattr(info.context.user, "current_profile", None)
        return profile.pk if profile else None


application = GraphQLWSAPIKeyConsumer.as_asgi(schema=strawberry.Schema(query=Query))


async def _query(params: dict, query: str) -> dict:
    async with GraphQLWebsocketCommunicator(
        application, "/graphql", connection_params=params
    ) as ws:
        async for result in ws.subscribe(query):
            return result.data


async def _whoami(params: dict) -> str | None:
    return (await _query(params, "{ whoami }"))["whoami"]


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


async def test_current_profile_header_is_honored() -> None:
    from baseapp_profiles.tests.factories import ProfileFactory

    api_key = await database_sync_to_async(f.APIKeyFactory)()
    unencrypted = await database_sync_to_async(APIKey.objects.decrypt)(
        encrypted_value=api_key.encrypted_api_key
    )
    own, other = await database_sync_to_async(
        lambda: (ProfileFactory(owner=api_key.user), ProfileFactory())
    )()
    own_id, other_id = await database_sync_to_async(lambda: (own.relay_id, other.relay_id))()

    data = await _query(
        {"HTTP_API_KEY": unencrypted, "Current-Profile": own_id}, "{ currentProfileId }"
    )
    assert data["currentProfileId"] == own.pk
    data = await _query(
        {"HTTP_API_KEY": unencrypted, "Current-Profile": other_id}, "{ currentProfileId }"
    )
    assert data["currentProfileId"] is None


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
async def test_current_profile_header_is_ignored_without_baseapp_profiles(
    with_disabled_apps,
) -> None:
    from baseapp_profiles.tests.factories import ProfileFactory

    api_key = await database_sync_to_async(f.APIKeyFactory)()
    unencrypted = await database_sync_to_async(APIKey.objects.decrypt)(
        encrypted_value=api_key.encrypted_api_key
    )
    email, own_id = await database_sync_to_async(
        lambda: (api_key.user.email, ProfileFactory(owner=api_key.user).relay_id)
    )()
    params = {"HTTP_API_KEY": unencrypted, "Current-Profile": own_id}

    data = await _query(params, "{ whoami currentProfileId }")
    assert data == {"whoami": email, "currentProfileId": None}
