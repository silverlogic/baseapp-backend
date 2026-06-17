import logging as _logging
import traceback
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

from .decorators import graphql_schema_required


def get_pk_from_relay_id(relay_id):
    from baseapp_core.hashids.strategies import (
        graphql_get_pk_from_global_id_using_strategy,
    )

    return graphql_get_pk_from_global_id_using_strategy(relay_id)


def get_obj_from_relay_id(info: graphene.ResolveInfo, relay_id, get_node=False):
    from baseapp_core.hashids.strategies import (
        graphql_get_instance_from_global_id_using_strategy,
    )

    return graphql_get_instance_from_global_id_using_strategy(info, relay_id, get_node)


@graphql_schema_required
def get_obj_relay_id(obj):
    from baseapp_core.hashids.strategies import graphql_to_global_id_using_strategy

    object_type = _cache_object_type(obj)
    if not object_type:
        raise Exception(f"Model {obj.__class__.__name__} does not inherit from RelayModel")
    return graphql_to_global_id_using_strategy(obj, object_type._meta.name, obj.pk)


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


def resolve_document_content_object(
    document,
    info: "graphene.ResolveInfo",
    *,
    cache_attr: str = "_document_content_object_cache",
):
    """
    Resolve a `DocumentId.content_object` through a request-scoped cache so a
    connection of objects (each pointing at a `DocumentId`) doesn't hit the DB once
    per row to fetch the same kind of target.

    Two callers fan out from this helper:

    - `baseapp_follows` resolves `Follow.actor` / `Follow.target` (both FKs to
      `DocumentId`) into the underlying `Profile` (or any other model).
    - `baseapp_comments` resolves `Comment.target_document` into the model the
      comment was attached to.

    When the parent queryset prefetched the GFK via `GenericPrefetch`, accessing
    `document.content_object` returns the prefetched instance with no extra DB hit.
    The fallback path only fires for content types that weren't pre-warmed; even then,
    the request cache collapses calls to the same `(content_type_id, object_id)`
    pair into a single fetch per request.

    Pass a unique `cache_attr` if you need to keep follow / comment caches separate
    on the same request — but a shared cache across packages is also fine since the
    cache key is `(content_type_id, object_id)`.
    """
    if document is None:
        return None

    request_cache = getattr(info.context, cache_attr, None)
    if request_cache is None:
        request_cache = {}
        setattr(info.context, cache_attr, request_cache)

    cache_key = (document.content_type_id, document.object_id)
    if cache_key in request_cache:
        return request_cache[cache_key]

    obj = document.content_object
    request_cache[cache_key] = obj
    return obj


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
