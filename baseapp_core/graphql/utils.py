import logging as _logging
import traceback
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import graphene
import sqlparse
from django import db
from django.db.backends import utils as _django_utils
from django.db.models.sql import compiler as _compiler
from django.db.models.sql import query as _query
from graphene_django import views as _views
from graphene_django.debug.sql import tracking as _tracking
from graphene_django.registry import get_global_registry

_registry_map = None


def _get_registry_map():
    global _registry_map
    if _registry_map is None:
        _registry_map = {
            object_type._meta.name: model
            for model, object_type in get_global_registry()._registry.items()
        }
    return _registry_map


def get_pk_from_relay_id(relay_id):
    from baseapp_core.hashids.strategies import (
        graphql_get_pk_from_global_id_using_strategy,
    )

    return graphql_get_pk_from_global_id_using_strategy(relay_id)


def get_obj_from_relay_id(info: graphene.ResolveInfo, relay_id, get_node=False):
    if get_node is not False:
        warnings.warn(
            "The 'get_node' parameter of 'get_obj_from_relay_id' is deprecated and will be removed in a future version. "
            "Please update your code to not use this parameter.",
            DeprecationWarning,
            stacklevel=2,
        )
    from baseapp_core.hashids.strategies import (
        graphql_get_node_from_global_id_using_strategy,
    )

    return graphql_get_node_from_global_id_using_strategy(info, relay_id)


def get_obj_relay_id(obj):
    from baseapp_core.hashids.strategies import graphql_to_global_id_using_strategy

    object_type = _cache_object_type(obj)
    return graphql_to_global_id_using_strategy(object_type._meta.name, obj.pk)


def _cache_object_type(obj):
    if not hasattr(obj, "_graphql_object_type"):
        registry = get_global_registry()
        obj._graphql_object_type = registry.get_type_for_model(obj._meta.concrete_model)

        # if not found for concret_model, try with the base model
        if not obj._graphql_object_type:
            obj._graphql_object_type = registry.get_type_for_model(obj._meta.model)

    return obj._graphql_object_type


def get_object_type_for_model(model):
    def get_object_type():
        return model.get_graphql_object_type()

    return get_object_type


def get_model_from_graphql_object_type(object_type_name: str):
    return _get_registry_map().get(object_type_name)


BASE_PATH = str(Path(__file__).parent.parent.parent.resolve())
SKIP_PATHS = [
    str(Path(_query.__file__).resolve()),
    str(Path(_compiler.__file__).resolve()),
    str(Path(_tracking.__file__).resolve()),
    str(Path(_django_utils.__file__).resolve()),
    str(Path(_logging.__file__).resolve()),
]
STOP_PATH = str(Path(_views.__file__).resolve())


@dataclass
class QueryData:
    queries: list[str]
    stacks: list[str]

    def __str__(self) -> str:
        return f"QueryData with {len(self.queries)} queries."

    def __repr__(self) -> str:
        return "QueryData(queries=..., stacks=...)"

    @property
    def count(self) -> int:
        return len(self.queries)

    @property
    def log(self) -> str:
        message = "\n" + "-" * 75
        message += f"\n>>> Queries ({len(self.queries)}):\n\n"

        query: str
        summary: str
        for index, (query, summary) in enumerate(zip(self.queries, self.stacks, strict=False)):
            message += f"{index + 1})"
            message += "\n\n"
            message += "--- Query ".ljust(75, "-")
            message += "\n\n"
            message += sqlparse.format(query, reindent=True)
            message += "\n\n"
            message += "--- Stack (abridged) ".ljust(75, "-")
            message += "\n\n"
            message += summary
            message += "\n"
            message += "-" * 75
            message += "\n\n"

        message += "-" * 75
        return message

    def __getitem__(self, item: int) -> str:
        # In order to access QueryData like a list (ex: query_data[0])
        return self.queries[item]


def db_query_logger(
    execute,
    sql,
    params,
    many,  # noqa: FBT001
    context,
    query_data: QueryData,
):
    """
    A database query logger for capturing executed database queries.
    Used to check that query optimizations work as expected.

    Can also be used as a place to put debugger breakpoint for solving issues.
    """
    query_data.stacks.append(get_stack_info())

    # Don't include transaction creation, as we aren't interested in them.

    if (
        not sql.startswith("SAVEPOINT")
        and not sql.startswith("RELEASE SAVEPOINT")
        and not sql.startswith("ROLLBACK")
        and not sql.startswith('SELECT "constance_constance"."id"')
        and not sql.startswith('INSERT INTO "constance_constance"')
    ):
        try:
            query_data.queries.append(sql % params)
        except TypeError:
            query_data.queries.append(sql)
    return execute(sql, params, many, context)


def get_stack_info() -> str:
    # Get the current stack for debugging purposes.
    # Don't include files from the skipped paths.
    stack: list[traceback.FrameSummary] = []
    skipped = 0  # How many frames have been skipped?
    to_skip = 2  # Skip the first two frames (this func and caller func)

    for frame in reversed(traceback.extract_stack()):
        if skipped < to_skip:
            skipped += 1
            continue

        is_skipped_path = any(frame.filename.startswith(path) for path in SKIP_PATHS)
        if is_skipped_path:
            continue

        is_stop_path = frame.filename.startswith(STOP_PATH)
        if is_stop_path:
            break

        stack.insert(0, frame)

        is_own_file = frame.filename.startswith(BASE_PATH)
        if is_own_file:
            break

    return "".join(traceback.StackSummary.from_list(stack).format())


# Credit to MrThearMan https://github.com/MrThearMan/graphene-django-query-optimizer/blob/fa240c4816f5d36f709933b6b00bc51d4dff6af5/example_project/app/utils.py#L134
@contextmanager
def capture_database_queries():
    """Capture results of what database queries were executed. `DEBUG` needs to be set to True."""
    query_data = QueryData(queries=[], stacks=[])
    query_logger = partial(db_query_logger, query_data=query_data)

    with db.connection.execute_wrapper(query_logger):
        yield query_data
