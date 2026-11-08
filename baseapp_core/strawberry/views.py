from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from strawberry.django.views import GraphQLView as StrawberryGraphQLView
from strawberry.http import GraphQLHTTPResponse
from strawberry.types import ExecutionResult


class GraphQLView(StrawberryGraphQLView):
    """Strawberry view whose `info.context` is the Django request, like Graphene's.

    Keeping `info.context.user` / `info.context.headers` lets services written for Graphene
    resolvers run unchanged. Token and JWT auth replace the Graphene auth middlewares.
    """

    authenticators = (TokenAuthentication, JWTAuthentication)
    multipart_uploads_enabled = True

    def parse_multipart(self, request: Any) -> dict[str, Any]:
        """Accept the spec (`operations` + `map`) and the frontend's form: `query`, `variables`
        and files posted under their own keys, which mutations read from `info.context.FILES`."""
        post = request.post_data
        if "operations" in post:
            return super().parse_multipart(request)
        data: dict[str, Any] = {"query": post.get("query")}
        for key in ("variables", "extensions"):
            if post.get(key):
                data[key] = self.parse_json(post[key])
        if post.get("operationName"):
            data["operationName"] = post["operationName"]
        return data

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

    def process_result(self, request: HttpRequest, result: ExecutionResult) -> GraphQLHTTPResponse:
        # Like graphene-django: with ATOMIC_REQUESTS, a response carrying errors rolls back.
        if result.errors and connection.settings_dict.get("ATOMIC_REQUESTS", False):
            if connection.in_atomic_block:
                transaction.set_rollback(True)
        return super().process_result(request, result)
