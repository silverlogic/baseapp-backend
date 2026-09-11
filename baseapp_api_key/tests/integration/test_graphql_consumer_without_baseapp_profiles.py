from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from django.conf import settings

from baseapp_api_key.graphql.consumers import BaseGraphqlWsAPIKeyAuthenticatedConsumer

pytestmark = pytest.mark.django_db


def _build_api_key_model(api_key) -> tuple[SimpleNamespace, Mock]:
    queryset = Mock()
    queryset.filter.return_value = queryset
    queryset.first.return_value = api_key
    manager = Mock()
    manager.encrypt.return_value = b"encrypted"
    manager.select_related.return_value = queryset
    return SimpleNamespace(objects=manager), queryset


def _sync_to_async(func) -> Callable[..., Any]:
    async def runner(*args, **kwargs) -> Any:
        return func(*args, **kwargs)

    return runner


@pytest.mark.parametrize("with_disabled_apps", [["baseapp_profiles"]], indirect=True)
class TestApiKeyGraphqlConsumerWithoutBaseappProfiles:
    @pytest.mark.asyncio
    async def test_on_connect_authenticates_user_and_ignores_current_profile_header(
        self, with_disabled_apps
    ) -> None:
        user = SimpleNamespace(is_active=True)
        api_key = SimpleNamespace(is_expired=False, user=user)
        api_key_model, queryset = _build_api_key_model(api_key)
        consumer = SimpleNamespace(scope={}, APIKeyModel=api_key_model)
        payload = {
            settings.BA_API_KEY_REQUEST_HEADER: "plain-key",
            "Current-Profile": "fake-profile-relay-id",
        }

        with (
            patch(
                "baseapp_api_key.graphql.consumers.database_sync_to_async",
                side_effect=_sync_to_async,
            ),
            patch("baseapp_api_key.graphql.consumers.swapper.load_model") as load_model_mock,
        ):
            await BaseGraphqlWsAPIKeyAuthenticatedConsumer.on_connect(consumer, payload)

        assert consumer.scope["user"] is user
        assert not hasattr(user, "current_profile")
        api_key_model.objects.encrypt.assert_called_once_with(unencrypted_value="plain-key")
        queryset.filter.assert_called_once_with(encrypted_api_key=b"encrypted")
        load_model_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_connect_sets_anonymous_when_api_key_is_missing(
        self, with_disabled_apps
    ) -> None:
        consumer = SimpleNamespace(scope={})
        payload = {}

        await BaseGraphqlWsAPIKeyAuthenticatedConsumer.on_connect(consumer, payload)

        assert consumer.scope["user"].is_anonymous is True
