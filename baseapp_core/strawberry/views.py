from typing import Any

from django.http import HttpRequest, HttpResponse
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from strawberry.django.views import GraphQLView as StrawberryGraphQLView


class GraphQLView(StrawberryGraphQLView):
    """Strawberry view whose `info.context` is the Django request, like Graphene's.

    Keeping `info.context.user` / `info.context.headers` lets services written for Graphene
    resolvers run unchanged. Token and JWT auth replace the Graphene auth middlewares.
    """

    authenticators = (TokenAuthentication, JWTAuthentication)

    def get_context(self, request: HttpRequest, response: HttpResponse) -> Any:
        if not getattr(request, "_graphql_authenticated", False):
            for authenticator in self.authenticators:
                try:
                    auth = authenticator().authenticate(request)
                except (AuthenticationFailed, InvalidToken):
                    auth = None
                if auth and auth[0] and auth[0].is_authenticated:
                    request.user = auth[0]
                    break
            request._graphql_authenticated = True
        request.graphql_response = response
        return request
