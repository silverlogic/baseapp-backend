from typing import Any

from channels.db import database_sync_to_async
from django.conf import settings

from baseapp_api_key.models import APIKey, BaseAPIKey
from baseapp_core.strawberry.subscriptions import GraphQLWSConsumer


class BaseGraphQLWSAPIKeyConsumer(GraphQLWSConsumer):
    """Authenticates with the API key in `connectionParams[BA_API_KEY_REQUEST_HEADER]`."""

    APIKeyModel: type[BaseAPIKey]

    async def authenticate_connection(self, params: dict[str, Any]) -> Any:
        unencrypted_api_key = params.get(settings.BA_API_KEY_REQUEST_HEADER)
        if not isinstance(unencrypted_api_key, str):
            return None
        encrypted_api_key = self.APIKeyModel.objects.encrypt(unencrypted_value=unencrypted_api_key)
        api_key = await database_sync_to_async(
            self.APIKeyModel.objects.select_related("user")
            .filter(encrypted_api_key=encrypted_api_key)
            .first
        )()
        if api_key is None or api_key.is_expired:
            return None
        return api_key.user


class GraphQLWSAPIKeyConsumer(BaseGraphQLWSAPIKeyConsumer):
    APIKeyModel = APIKey
