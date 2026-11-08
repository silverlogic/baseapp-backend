import functools
from collections.abc import Callable
from typing import Any

import strawberry
from django.utils.translation import gettext_lazy as _
from strawberry.permission import BasePermission
from strawberry.types import Info


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
