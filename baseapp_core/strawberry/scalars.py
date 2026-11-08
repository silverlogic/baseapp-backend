"""Scalars Graphene exposes that Strawberry has no built-in for (same names and wire format)."""

import json
from typing import Any, NewType

import strawberry

JSONString = strawberry.scalar(
    NewType("JSONString", object),
    name="JSONString",
    description="Allows use of a JSON String for input / output from the GraphQL schema.",
    serialize=lambda value: json.dumps(value),
    parse_value=lambda value: json.loads(value),
)

GenericScalar = strawberry.scalar(
    NewType("GenericScalar", object),
    name="GenericScalar",
    description="The `GenericScalar` scalar type represents a generic GraphQL scalar value.",
    serialize=lambda value: value,
    parse_value=lambda value: value,
)


def _big_int(value: Any) -> int:
    return int(value)


BigInt = strawberry.scalar(
    NewType("BigInt", int),
    name="BigInt",
    description="Integers that can exceed the 32-bit range of `Int`.",
    serialize=_big_int,
    parse_value=_big_int,
)
