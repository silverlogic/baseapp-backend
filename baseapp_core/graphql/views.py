import json
import logging
from contextlib import contextmanager

import pghistory
from django.http.response import HttpResponseBadRequest
from graphene_django.views import GraphQLView as GrapheneGraphQLView
from graphene_django.views import HttpError
from graphql import get_operation_ast, parse
from graphql.execution import ExecutionResult

try:
    import sentry_sdk
    from sentry_sdk.consts import OP
except ModuleNotFoundError:
    sentry_sdk = None


@contextmanager
def sentry_graphql_span(operation_name, operation_type):
    if sentry_sdk:
        op = OP.GRAPHQL_QUERY
        if operation_type == "mutation":
            op = OP.GRAPHQL_MUTATION
        elif operation_type == "subscription":
            op = OP.GRAPHQL_SUBSCRIPTION

        with sentry_sdk.start_transaction(op=op, name=operation_name):
            yield
    else:
        yield


class GraphQLView(GrapheneGraphQLView):
    def execute_graphql_request(
        self, request, data, query, variables, operation_name, show_graphiql=False
    ):
        if not query:
            if show_graphiql:
                return None
            raise HttpError(HttpResponseBadRequest("Must provide query string."))

        try:
            document = parse(query)
        except Exception as e:
            logging.exception(e)
            return ExecutionResult(errors=[e])

        operation_ast = get_operation_ast(document, operation_name)
        operation_name = (
            operation_ast.name.value
            if operation_ast and operation_ast.name and not operation_name
            else operation_name
        )
        operation_type = operation_ast.operation.value

        with sentry_graphql_span(operation_name, operation_type):
            with pghistory.context(
                graphql_operation_name=operation_name, graphql_operation_type=operation_type
            ):
                return super().execute_graphql_request(
                    request, data, query, variables, operation_name, show_graphiql
                )

    def parse_body(self, request):
        """Handle multipart request spec for multipart/form-data"""
        content_type = self.get_content_type(request)
        # logging.info('content_type: %s' % content_type)
        # import pdb; pdb.set_trace()
        if content_type == "multipart/form-data" and "operations" in request.POST:
            operations = json.loads(request.POST.get("operations", "{}"))
            # import pdb; pdb.set_trace()
            files_map = json.loads(request.POST.get("map", "{}"))
            from graphene_file_upload.utils import place_files_in_operations

            return place_files_in_operations(operations, files_map, request.FILES)
        return super(GraphQLView, self).parse_body(request)
