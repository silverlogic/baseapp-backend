import sys
import typing

import channels_graphql_ws
import swapper
from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from graphene_django.settings import graphene_settings

from baseapp_api_key.models import APIKey, BaseAPIKey
from baseapp_core.graphql import get_pk_from_relay_id

python_version = sys.version_info

Profile = swapper.load_model("baseapp_profiles", "Profile")

from baseapp_core.graphql.consumers import threadpool_for_sync_resolvers


class BaseGraphqlWsAPIKeyAuthenticatedConsumer(channels_graphql_ws.GraphqlWsConsumer):
    APIKeyModel: typing.Type[BaseAPIKey]
    middleware = [threadpool_for_sync_resolvers]

    schema = graphene_settings.SCHEMA

    async def on_connect(self, payload):
        if "user" in self.scope:
            # do nothing if already authenticated
            return

        if settings.BA_API_KEY_REQUEST_HEADER not in payload:
            self.scope["user"] = AnonymousUser()
            return

        user = None
        unencrypted_api_key = payload[settings.BA_API_KEY_REQUEST_HEADER]

        if isinstance(unencrypted_api_key, str):
            encrypted_api_key = self.APIKeyModel.objects.encrypt(
                unencrypted_value=unencrypted_api_key
            )
            api_key = await database_sync_to_async(
                self.APIKeyModel.objects.all().filter(encrypted_api_key=encrypted_api_key).first
            )()

            if api_key is None:
                user = None

            if api_key.is_expired:
                user = None

            user = api_key.user

        if user and user.is_active:
            self.scope["user"] = user
            if "Current-Profile" in payload:
                pk = get_pk_from_relay_id(payload["Current-Profile"])
                if pk:
                    profile = await database_sync_to_async(Profile.objects.filter(pk=pk).first)()
                    if profile and database_sync_to_async(user.has_perm)(
                        f"{profile._meta.app_label}.use_profile", profile
                    ):
                        user.current_profile = profile
        else:
            self.scope["user"] = AnonymousUser()
            return


class GraphqlWsAPIKeyAuthenticatedConsumer(BaseGraphqlWsAPIKeyAuthenticatedConsumer):
    APIKeyModel = APIKey
