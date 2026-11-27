from typing import Any

from baseapp_auth.rest_framework.authentication import AllAuthJWTTokenAuthentication


class AllauthJWTTokenAuthentication(AllAuthJWTTokenAuthentication):
    """GraphQL middleware that authenticates allauth headless JWT access tokens.

    A token allauth doesn't recognise leaves the request untouched for the next middleware.
    """

    def resolve(self, next, root, info, **kwargs) -> Any:
        context = info.context

        if not getattr(context, "_allauth_jwt_checked", False):
            auth = self.authenticate(context)
            if auth:
                user, _ = auth
                if user and user.is_authenticated:
                    context.user = user
            context._allauth_jwt_checked = True

        return next(root, info, **kwargs)
