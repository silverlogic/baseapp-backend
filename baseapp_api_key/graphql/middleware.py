from baseapp_api_key.rest_framework.authentication import (
    APIKeyAuthentication as RestAPIKeyAuthentication,
)


class APIKeyAuthentication(RestAPIKeyAuthentication):
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
