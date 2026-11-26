from collections.abc import Callable
from typing import TYPE_CHECKING

import graphene
from graphene_django.registry import get_global_registry

from baseapp_core.testing.queries import (  # noqa: F401 - moved; kept importable from here
    QueryData,
    capture_database_queries,
    db_query_logger,
    get_stack_info,
)

from .decorators import graphql_schema_required

if TYPE_CHECKING:
    from django.db.models import Model

    from .object_types import DjangoObjectType


def get_pk_from_relay_id(relay_id) -> int | str:
    from baseapp_core.hashids.strategies import (
        graphql_get_pk_from_global_id_using_strategy,
    )

    return graphql_get_pk_from_global_id_using_strategy(relay_id)


def get_obj_from_relay_id(info: graphene.ResolveInfo, relay_id, get_node=False) -> "Model":
    from baseapp_core.hashids.strategies import (
        graphql_get_instance_from_global_id_using_strategy,
    )

    return graphql_get_instance_from_global_id_using_strategy(info, relay_id, get_node)


@graphql_schema_required
def get_obj_relay_id(obj) -> str:
    from baseapp_core.hashids.strategies import graphql_to_global_id_using_strategy

    object_type = _cache_object_type(obj)
    if not object_type:
        raise Exception(f"Model {obj.__class__.__name__} does not inherit from RelayModel")
    return graphql_to_global_id_using_strategy(obj, object_type._meta.name, obj.pk)


def _cache_object_type(obj) -> "type[DjangoObjectType] | None":
    if not hasattr(obj, "_graphql_object_type"):
        registry = get_global_registry()
        obj._graphql_object_type = registry.get_type_for_model(obj._meta.concrete_model)

        # if not found for concret_model, try with the base model
        if not obj._graphql_object_type:
            obj._graphql_object_type = registry.get_type_for_model(obj._meta.model)

    return obj._graphql_object_type


def get_object_type_for_model(model) -> Callable[[], "type[DjangoObjectType]"]:
    def get_object_type() -> "type[DjangoObjectType]":
        return model.get_graphql_object_type()

    return get_object_type


def resolve_document_content_object(
    document,
    info: "graphene.ResolveInfo",
    *,
    cache_attr: str = "_document_content_object_cache",
) -> "Model | None":
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
