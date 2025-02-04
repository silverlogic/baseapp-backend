import logging
import traceback

from rest_framework.authentication import TokenAuthentication as RestTokenAuthentication
from rest_framework_simplejwt.authentication import (
    JWTAuthentication as RestJWTAuthentication,
)


class LogExceptionMiddleware(object):
    def on_error(self, error):
        # need to raise error again to get access to traceback
        try:
            raise error
        except Exception as error:
            # sends to sentry
            logging.exception(error)

            # prints to stdout
            traceback.print_exc()
            raise error

    def resolve(self, next, root, info, **args):
        response = next(root, info, **args)

        if isinstance(response, Exception):
            self.on_error(response)
        elif hasattr(response, "catch"):
            return response.catch(self.on_error)

        return response


class TokenAuthentication(RestTokenAuthentication):
    authenticated = False

    def resolve(self, next, root, info, **kwargs):
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

    def resolve(self, next, root, info, **kwargs):
        if not self.authenticated:
            auth = self.authenticate(info.context)
            if auth:
                user = auth[0]
                if user and user.is_authenticated:
                    info.context.user = user
            self.authenticated = True
        return next(root, info, **kwargs)
