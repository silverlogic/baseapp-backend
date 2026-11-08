import logging
from collections.abc import Generator

import pghistory
from graphql import GraphQLError
from strawberry.extensions import SchemaExtension

from baseapp_core.graphql.views import sentry_graphql_span


class OperationContextExtension(SchemaExtension):
    """Sentry transaction + pghistory context per operation, as `baseapp_core.graphql.GraphQLView` does."""

    def on_execute(self) -> Generator[None, None, None]:
        execution_context = self.execution_context
        operation_type = execution_context.operation_type.value
        operation_name = execution_context.operation_name
        with sentry_graphql_span(operation_name, operation_type):
            with pghistory.context(
                graphql_operation_name=operation_name, graphql_operation_type=operation_type
            ):
                yield


def log_unexpected_errors(errors: list[GraphQLError]) -> None:
    """Log resolver exceptions (Sentry) but not client-facing `GraphQLError`s."""
    for error in errors:
        original = error.original_error
        if original is not None and not isinstance(original, GraphQLError):
            logging.exception(original, exc_info=original)
