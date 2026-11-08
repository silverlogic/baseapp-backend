from typing import Any

from django.conf import settings
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse
from django.utils.module_loading import import_string
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken
from strawberry.django.views import GraphQLView as StrawberryGraphQLView
from strawberry.http import GraphQLHTTPResponse
from strawberry.types import ExecutionResult


def authenticator_classes() -> list[type[BaseAuthentication]]:
    """`STRAWBERRY_AUTHENTICATION_CLASSES`, or the DRF authentication classes listed in
    `GRAPHENE["MIDDLEWARE"]` so both endpoints authenticate the same way while they coexist."""
    configured = getattr(settings, "STRAWBERRY_AUTHENTICATION_CLASSES", None)
    if configured is None:
        configured = [
            path
            for path in getattr(settings, "GRAPHENE", {}).get("MIDDLEWARE", ())
            if issubclass(import_string(path), BaseAuthentication)
        ]
    return [import_string(path) if isinstance(path, str) else path for path in configured]


class GraphQLView(StrawberryGraphQLView):
    """Strawberry view whose `info.context` is the Django request, like Graphene's.

    Keeping `info.context.user` / `info.context.headers` lets services written for Graphene
    resolvers run unchanged. DRF authentication classes replace the Graphene auth middlewares.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("multipart_uploads_enabled", True)
        super().__init__(*args, **kwargs)

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
            for authenticator in authenticator_classes():
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
        response_data = super().process_result(request, result)
        # Like graphene-django: errors without a path (syntax, validation) are a 400 with no data.
        if result.errors and any(not error.path for error in result.errors):
            response_data.pop("data", None)
            if sub_response := getattr(request, "graphql_response", None):
                sub_response.status_code = 400
        return response_data
