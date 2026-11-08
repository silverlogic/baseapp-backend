import dataclasses
import enum
import functools
from collections.abc import Callable
from typing import Any

import strawberry
from django.utils.translation import gettext_lazy as _
from rest_framework.exceptions import ErrorDetail
from rest_framework.serializers import Serializer
from strawberry.permission import BasePermission
from strawberry.types import Info
from strawberry.types.unset import UnsetType


@strawberry.type(name="ErrorType")
class ErrorType:
    field: str
    messages: list[str]


class IsAuthenticated(BasePermission):
    """Same error shape as `baseapp_core.graphql.login_required`."""

    error_extensions = {"code": "authentication_required"}

    @property
    def message(self) -> str:
        return str(_("authentication required"))

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        return info.context.user.is_authenticated


@strawberry.input
class RelayMutationInput:
    client_mutation_id: str | None = None


@strawberry.type
class RelayMutationPayload:
    """Base payload matching Graphene's `RelayMutation` (`clientMutationId` + `errors`)."""

    client_mutation_id: str | None = None
    errors: list[ErrorType | None] | None = strawberry.field(
        default=None, description=str(_("May contain more than one error for same field."))
    )


def relay_mutation(
    resolver: Callable | None = None, *, login_required: bool = False, **field_kwargs: Any
) -> Any:
    """Declare a Relay-style mutation: `name(input: XInput!): XPayload`, echoing `clientMutationId`."""

    def decorator(func: Callable) -> Any:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            payload = func(*args, **kwargs)
            mutation_input = kwargs.get("input")
            if payload is not None and mutation_input is not None:
                payload.client_mutation_id = mutation_input.client_mutation_id
            return payload

        if login_required:
            field_kwargs.setdefault("permission_classes", [IsAuthenticated])
        field_kwargs.setdefault("description", func.__doc__)
        return strawberry.mutation(resolver=wrapper, **field_kwargs)

    return decorator(resolver) if resolver else decorator


def input_data(mutation_input: Any, *, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    """Input fields the client actually sent, snake_cased, like Graphene's `**input`.

    Optional input fields should default to `strawberry.UNSET` so omitted fields stay omitted.
    """
    data = {}
    for f in dataclasses.fields(mutation_input):
        value = getattr(mutation_input, f.name)
        if f.name == "client_mutation_id" or f.name in exclude or isinstance(value, UnsetType):
            continue
        data[f.name] = value.value if isinstance(value, enum.Enum) else value
    return data


def add_request_files(info: Info, data: dict[str, Any]) -> dict[str, Any]:
    """Files posted next to the operation, keyed by snake_cased name (SerializerMutation contract)."""
    from django.utils.text import camel_case_to_spaces

    for name, values in info.context.FILES.lists():
        key = camel_case_to_spaces(name).replace(" ", "_")
        data[key] = values[0] if len(values) == 1 else values
    return data


def serializer_errors(serializer: Serializer) -> list[ErrorType]:
    """Flatten DRF errors exactly like `baseapp_core.graphql.SerializerMutation`."""
    errors: dict[str, list[str]] = {}
    for field_name, messages in serializer.errors.items():
        index = 0
        for message in messages:
            if isinstance(message, ErrorDetail):
                errors.setdefault(field_name, []).append(str(message))
            else:
                for field, msg in message.items():
                    errors.setdefault(f"{field_name}.{index}.{field}", []).append(msg[0].title())
                index += 1
    return [ErrorType(field=key, messages=value) for key, value in errors.items()]


@strawberry.input(name="DeleteNodeInput")
class DeleteNodeInput(RelayMutationInput):
    id: strawberry.ID


@strawberry.type(name="DeleteNodePayload")
class DeleteNodePayload(RelayMutationPayload):
    deleted_id: strawberry.ID = strawberry.field(name="deletedID")


def delete_node(info: Info, input: DeleteNodeInput) -> DeleteNodePayload:
    """`baseapp_core.graphql.DeleteNode`: delete any node the user has `delete_<model>` on."""
    from .relay import get_instance_from_global_id

    obj = get_instance_from_global_id(info, input.id)
    error = PermissionError(_("You don't have permission to delete this."))
    if not obj:
        raise error
    opts = obj._meta
    if not info.context.user.has_perm(f"{opts.app_label}.delete_{opts.model_name}", obj):
        raise error
    obj.delete()
    return DeleteNodePayload(deleted_id=input.id)


def delete_node_mutation(**kwargs: Any) -> Any:
    def resolver(info: Info, input: DeleteNodeInput) -> DeleteNodePayload | None:
        return delete_node(info, input)

    return relay_mutation(resolver, login_required=True, **kwargs)


class _InputDict(dict):
    """Graphene `InputObjectType` values support both `value["x"]` and `value.x`."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error


def _to_graphene_value(value: Any) -> Any:
    from django.db.models import Choices

    if isinstance(value, enum.Enum):
        return value if isinstance(value, Choices) else value.value
    if isinstance(value, list):
        return [_to_graphene_value(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _InputDict(
            {
                f.name: _to_graphene_value(getattr(value, f.name))
                for f in dataclasses.fields(value)
                if not isinstance(getattr(value, f.name), UnsetType)
            }
        )
    return value


def graphene_input(mutation_input: Any) -> dict[str, Any]:
    """The `**input` a Graphene `mutate_and_get_payload` receives for this Strawberry input."""
    data = _to_graphene_value(mutation_input)
    data.pop("client_mutation_id", None)
    return dict(data)


def _from_graphene_value(value: Any) -> Any:
    from .connections import Edge

    if isinstance(value, list):
        return [_from_graphene_value(v) for v in value]
    class_name = type(value).__name__
    if class_name == "ErrorType" and hasattr(value, "messages"):
        return ErrorType(field=value.field, messages=list(value.messages))
    if class_name.endswith("Edge") and hasattr(value, "node") and hasattr(value, "cursor"):
        return Edge(node=value.node, cursor=value.cursor)
    return value


def delegate_to_graphene(
    graphene_mutation: Any, info: Info, mutation_input: Any, payload_type: type
) -> Any:
    """Run a Graphene mutation's `mutate_and_get_payload` and map its result onto `payload_type`.

    Both endpoints then share one implementation while the schemas coexist; when Graphene is
    removed the logic moves out of the Graphene class.
    """
    result = graphene_mutation.mutate_and_get_payload(None, info, **graphene_input(mutation_input))
    if result is None:
        return None
    values = {
        f.name: _from_graphene_value(getattr(result, f.name, None))
        for f in dataclasses.fields(payload_type)
        if f.name != "client_mutation_id"
    }
    return payload_type(**values)


def graphene_relay_mutation(
    graphene_mutation: Any, input_type: type, payload_type: type, **field_kwargs: Any
) -> Any:
    """A Strawberry Relay mutation whose logic is the Graphene mutation's (see `delegate_to_graphene`)."""

    def resolver(info: Info, input: input_type) -> payload_type | None:  # type: ignore[valid-type]
        return delegate_to_graphene(graphene_mutation, info, input, payload_type)

    field_kwargs.setdefault("description", graphene_mutation.__doc__)
    return relay_mutation(resolver, **field_kwargs)
