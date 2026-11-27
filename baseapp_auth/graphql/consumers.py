import logging
from typing import TYPE_CHECKING

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

from baseapp_core.graphql.consumers import GraphqlWsJWTAuthenticatedConsumer

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_allauth_jwt_user(access_token: str) -> "AbstractBaseUser | None":
    """Return the user for a valid allauth headless JWT access token, or ``None``.

    With stateful validation on (the default), a token whose session was ended by
    logout is rejected.
    """
    from allauth.headless.tokens.strategies.jwt.internal import validate_access_token

    try:
        result = validate_access_token(access_token)
    except Exception:
        logger.exception("allauth JWT access token validation failed")
        return None
    if result is None:
        return None
    _, payload = result
    return get_user_model().objects.filter(pk=payload["sub"]).first()


class GraphqlWsAllAuthJWTAuthenticatedConsumer(GraphqlWsJWTAuthenticatedConsumer):
    """GraphQL websocket consumer that accepts allauth headless JWT access tokens.

    Tokens allauth doesn't accept fall back to the SimpleJWT handling of the base
    consumer, so clients still on the SimpleJWT strategy keep working.
    """

    async def authenticate(self, payload: dict) -> "AbstractBaseUser | None":
        user = await get_allauth_jwt_user(payload["Authorization"])
        if user is not None:
            return user
        return await super().authenticate(payload)
