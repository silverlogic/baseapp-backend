import logging

from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import UntypedToken

from baseapp_core.graphql.consumers import GraphqlWsJWTAuthenticatedConsumer


class GraphqlWsAllAuthJWTAuthenticatedConsumer(GraphqlWsJWTAuthenticatedConsumer):
    @database_sync_to_async
    def get_jwt_user_instance(self, token_key):

        if self._auth is None or self._exceptions is None:
            raise RuntimeError("The _setup method must be called first.")

        try:
            untyped_token = UntypedToken(token_key)
            return self._auth.get_user(untyped_token)
        except self._exceptions as e:
            logging.error(e)
            return None
