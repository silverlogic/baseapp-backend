import logging

from rest_framework.authentication import TokenAuthentication as RestTokenAuthentication


class LogExceptionMiddleware(object):
    def on_error(self, error):
        # need to raise error again to get access to traceback
        try:
            raise error
        except Exception as error:
            logging.exception(error)
            raise error

    def resolve(self, next, root, info, **args):
        response = next(root, info, **args)
        if hasattr(response, "catch"):
            return response.catch(self.on_error)
        return response


class TokenAuthentication(RestTokenAuthentication):
    def resolve(self, next, root, info, **kwargs):
        auth = self.authenticate(info.context)
        if auth:
            user = auth[0]
            if user and user.is_authenticated:
                info.context.user = user
        return next(root, info, **kwargs)
