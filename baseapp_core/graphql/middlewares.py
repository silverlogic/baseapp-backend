import logging
import traceback
from typing import Any

from graphql import GraphQLError
from rest_framework.authentication import TokenAuthentication as RestTokenAuthentication
from rest_framework_simplejwt.authentication import (
    JWTAuthentication as RestJWTAuthentication,
)

# `GraphQLError` codes that answer an expected client condition (e.g. `login_required` on an
# anonymous request), not a server fault: returned to the client, but not logged as errors.
UNLOGGED_ERROR_CODES = frozenset({"authentication_required"})


def is_expected_client_error(error: BaseException) -> bool:
    """Whether `error` is a deliberate client-facing `GraphQLError` that should not be logged."""
    if not isinstance(error, GraphQLError):
        return False
    return (error.extensions or {}).get("code") in UNLOGGED_ERROR_CODES


class LogExceptionMiddleware(object):
    def on_error(self, error) -> None:
        if is_expected_client_error(error):
            raise error

        # need to raise error again to get access to traceback
        try:
            raise error
        except Exception as error:
            # sends to sentry
            logging.exception(error)

            # prints to stdout
            traceback.print_exc()
            raise error

    def resolve(self, next, root, info, **args) -> Any:
        response = next(root, info, **args)

        if isinstance(response, Exception):
            self.on_error(response)
        elif hasattr(response, "catch"):
            return response.catch(self.on_error)

        return response


class TokenAuthentication(RestTokenAuthentication):
    authenticated = False

    def resolve(self, next, root, info, **kwargs) -> Any:
        if not self.authenticated:
            auth = self.authenticate(info.context)
            if auth:
                user = auth[0]
                if user and user.is_authenticated:
                    info.context.user = user
            self.authenticated = True
        return next(root, info, **kwargs)


class JWTAuthentication(RestJWTAuthentication):
    authenticated = False

    def resolve(self, next, root, info, **kwargs) -> Any:
        if not self.authenticated:
            auth = self.authenticate(info.context)
            if auth:
                user = auth[0]
                if user and user.is_authenticated:
                    info.context.user = user
            self.authenticated = True
        return next(root, info, **kwargs)
