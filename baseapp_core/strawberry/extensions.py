import logging
from collections.abc import Generator
from contextlib import contextmanager

import pghistory
from graphql import GraphQLError
from strawberry.extensions import SchemaExtension

try:
    import sentry_sdk
    from sentry_sdk.consts import OP
except ModuleNotFoundError:
    sentry_sdk = None


@contextmanager
def sentry_graphql_span(
    operation_name: str | None, operation_type: str
) -> Generator[None, None, None]:
    """A Sentry transaction named after the operation (when Sentry is installed)."""
    if not sentry_sdk:
        yield
        return
    op = {
        "mutation": OP.GRAPHQL_MUTATION,
        "subscription": OP.GRAPHQL_SUBSCRIPTION,
    }.get(operation_type, OP.GRAPHQL_QUERY)
    with sentry_sdk.start_transaction(op=op, name=operation_name):
        yield


class OperationContextExtension(SchemaExtension):
    """Sentry transaction + pghistory context per operation."""

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
