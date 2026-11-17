import logging
import traceback
from typing import Any

from django.db.models import QuerySet
from graphql import get_nullable_type, is_list_type
from rest_framework.authentication import TokenAuthentication as RestTokenAuthentication
from rest_framework_simplejwt.authentication import (
    JWTAuthentication as RestJWTAuthentication,
)


class LogExceptionMiddleware(object):
    def on_error(self, error) -> None:
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


class QuerySetToListMiddleware:
    """
    Evaluates a QuerySet returned for a list field into a list.

    graphql-core 3.3 completes any list value that has __aiter__ asynchronously, and QuerySet has
    it, so the sync GraphQLView would get an un-awaited coroutine instead of a result. A list keeps
    the synchronous completion graphql-core 3.2 used for QuerySets.
    """

    def resolve(self, next, root, info, **args) -> Any:
        response = next(root, info, **args)
        if isinstance(response, QuerySet) and is_list_type(get_nullable_type(info.return_type)):
            return list(response)
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
