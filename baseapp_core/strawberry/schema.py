from collections.abc import Iterable, Sequence
from typing import Any

import strawberry
from graphql import GraphQLError
from strawberry.extensions import SchemaExtension
from strawberry.tools import merge_types
from strawberry.types import ExecutionContext
from strawberry_django.optimizer import DjangoOptimizerExtension

from .extensions import OperationContextExtension, log_unexpected_errors
from .mutations import delete_node_mutation
from .registry import type_registry
from .relations import expose_all_relations
from .relay import node_field


@strawberry.type
class CoreQueries:
    node = node_field()


@strawberry.type
class CoreMutations:
    delete_node = delete_node_mutation()


class Schema(strawberry.Schema):
    def process_errors(
        self, errors: list[GraphQLError], execution_context: ExecutionContext | None = None
    ) -> None:
        log_unexpected_errors(errors)


def build_schema(
    *,
    queries: Iterable[type],
    mutations: Iterable[type] = (),
    extensions: Sequence[type[SchemaExtension] | SchemaExtension] = (),
    **schema_kwargs: Any,
) -> Schema:
    """Merge plugin root types into one schema with the optimizer and BaseApp extensions on.

    Every registered model type is included, after its relations are exposed.
    """
    expose_all_relations()
    registered = [entry.strawberry_type for entry in type_registry.entries().values()]
    schema_kwargs["types"] = [*schema_kwargs.get("types", ()), *dict.fromkeys(registered)]
    return Schema(
        query=merge_types("Query", (*queries, CoreQueries)),
        mutation=merge_types("Mutation", (*mutations, CoreMutations)),
        extensions=[DjangoOptimizerExtension, OperationContextExtension, *extensions],
        **schema_kwargs,
    )
