from django.http.response import HttpResponseBadRequest
from graphene_django.views import GraphQLView as GrapheneGraphQLView
from graphene_django.views import HttpError
from graphql import get_operation_ast, parse
from graphql.execution import ExecutionResult

try:
    import sentry_sdk
except ModuleNotFoundError:
    sentry_sdk = None


class GraphQLView(GrapheneGraphQLView):
    def execute_graphql_request(
        self, request, data, query, variables, operation_name, show_graphiql=False
    ):
        if not query:
            if show_graphiql:
                return None
            raise HttpError(HttpResponseBadRequest("Must provide query string."))

        if sentry_sdk:
            if sentry_sdk.Hub.current.scope.transaction:
                try:
                    document = parse(query)
                except Exception as e:
                    return ExecutionResult(errors=[e])

                operation_ast = get_operation_ast(document, operation_name)
                operation_type = operation_ast.operation.value

                if operation_name:
                    sentry_sdk.Hub.current.scope.transaction.name = operation_name
                if operation_type:
                    sentry_sdk.Hub.current.scope.transaction.op = operation_type

        return super().execute_graphql_request(
            request, data, query, variables, operation_name, show_graphiql
        )
