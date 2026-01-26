from allauth.headless.contrib.rest_framework.authentication import (
    JWTTokenAuthentication,
)


class AllauthJWTTokenAuthentication(JWTTokenAuthentication):
    def resolve(self, next, root, info, **kwargs):
        context = info.context

        if not getattr(context, "_allauth_jwt_checked", False):
            auth = self.authenticate(context)
            if auth:
                user, _ = auth
                if user and user.is_authenticated:
                    context.user = user
            context._allauth_jwt_checked = True

        return next(root, info, **kwargs)
