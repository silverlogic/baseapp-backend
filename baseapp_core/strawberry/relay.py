from typing import TYPE_CHECKING, Any, Optional

import strawberry
from django.db.models import Model, QuerySet
from graphql_relay import from_global_id
from strawberry.types import Info
from strawberry_django.optimizer import optimize
from strawberry_django.resolvers import django_resolver
from strawberry_django.utils.typing import get_django_definition

from baseapp_core.hashids.strategies import (
    _is_model_pk_compatible,
    _is_model_public_id_compatible,
    _is_public_id_logic_enabled,
    graphql_to_global_id_using_strategy,
)
from baseapp_core.hashids.utils import is_uuid4
from baseapp_core.models import DocumentId

from .registry import type_registry

if TYPE_CHECKING:
    from strawberry.types.base import StrawberryObjectDefinition


def strawberry_node_type(info: Info, type_name: str, only_type: Any = None) -> Any:
    """The Strawberry `Node` type named `type_name`, with Graphene's lookup errors."""
    origin = getattr(info.schema.get_type_by_name(type_name), "origin", None)
    if origin is None:
        raise Exception(f'Relay Node "{type_name}" not found in schema')
    if only_type is not None:
        assert origin is only_type, f"Must receive a {only_type.__name__} id."
    if not issubclass(origin, Node):
        raise Exception(f'ObjectType "{type_name}" does not implement the "Node" interface.')
    return origin


def model_from_info(info: Info) -> type[Model] | None:
    """Return the Django model behind the GraphQL type that owns the field being resolved."""
    type_def = info.schema.get_type_by_name(info._raw_info.parent_type.name)
    django_def = get_django_definition(getattr(type_def, "origin", None))
    return django_def.model if django_def else None


@strawberry.interface(name="Node", description="An object with an ID")
class Node:
    """Relay `Node` whose ids come from the hashids strategies, byte-identical to Graphene's."""

    @strawberry.field(name="id", description="The ID of the object")
    @django_resolver(qs_hook=None)  # may read DocumentId: async-safe in subscription payloads
    def global_id(self, info: Info) -> strawberry.ID:
        return strawberry.ID(
            graphql_to_global_id_using_strategy(self, info._raw_info.parent_type.name, self.pk)
        )

    @classmethod
    def resolve_id_attr(cls) -> str:
        """Lookup attribute strawberry-django uses when it lists this type's model nodes."""
        return "pk"

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        """Fetch one optimized instance. Override to add the per-object permission check."""
        model = get_django_definition(cls).model
        queryset: QuerySet = model._default_manager.filter(pk=pk)
        if get_queryset := getattr(cls, "get_queryset", None):
            queryset = get_queryset(queryset, info)
        return optimize(queryset, info).first()


def _attach_public_id_hint() -> None:
    from .types import PublicIdOptimizerStore

    Node.__strawberry_definition__.get_field("global_id").store = PublicIdOptimizerStore()


_attach_public_id_hint()


def decode_global_id(info: Info, global_id: str) -> tuple[type | None, Any]:
    """Map any supported global id (public id, pk, legacy base64) to `(strawberry type, pk)`."""
    if is_uuid4(global_id) and _is_public_id_logic_enabled():
        if found := DocumentId.get_content_type_and_id_by_public_id(global_id):
            content_type, pk = found
            model = content_type.model_class()
            if _is_model_public_id_compatible(model):
                return type_registry.get_type_for_model(model), pk
    if global_id.isdigit():
        # Same exception and text as the Graphene PK strategy.
        raise Exception("Can't resolve PK query without a specific type provided")
    type_name, pk = from_global_id(global_id)
    if not type_name:
        return None, None
    type_def: "StrawberryObjectDefinition | None" = info.schema.get_type_by_name(type_name)
    return getattr(type_def, "origin", None), pk


def get_instance_from_global_id(info: Info, global_id: str) -> Model | None:
    """Strawberry counterpart of `get_obj_from_relay_id`: no permission check, any strategy."""
    strawberry_type, pk = decode_global_id(info, global_id)
    if strawberry_type is None:
        return None
    model = get_django_definition(strawberry_type).model
    return model._default_manager.filter(pk=pk).first()


def resolve_node(info: Info, id: strawberry.ID) -> Node | None:
    if not id:
        return None
    strawberry_type, pk = decode_global_id(info, id)
    if strawberry_type is None or not issubclass(strawberry_type, Node):
        return None
    return strawberry_type.get_node(info, pk)


def node_field() -> Any:
    return strawberry.field(resolver=resolve_node, description="Fetches an object given its ID")


def typed_node_field(type_ref: Any, **kwargs: Any) -> Any:
    """Graphene's `Node.Field(SomeType)`: `field(id: ID!): SomeType`, rejecting other types' ids."""

    def resolver(info: Info, id: strawberry.ID) -> Any:
        expected = type_ref.resolve_type() if hasattr(type_ref, "resolve_type") else type_ref
        if id.isdigit():
            model = get_django_definition(expected).model
            if not _is_model_pk_compatible(model):
                raise Exception(f"{model.__name__} is not compatible with the PK strategy")
            return expected.get_node(info, int(id))
        strawberry_type, pk = decode_global_id(info, id)
        if strawberry_type is None:
            return None
        if strawberry_type is not expected:
            name = expected.__strawberry_definition__.name
            raise AssertionError(f"Must receive a {name} id.")
        return strawberry_type.get_node(info, pk)

    kwargs.setdefault("description", "The ID of the object")
    return strawberry.field(resolver=resolver, graphql_type=Optional[type_ref], **kwargs)
