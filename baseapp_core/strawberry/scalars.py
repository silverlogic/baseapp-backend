"""Scalars Graphene exposes that Strawberry has no built-in for (same names and wire format).

Annotate with the `NewType`s; `build_schema` maps them through `StrawberryConfig.scalar_map`.
"""

import json
from typing import Any, NewType

import strawberry

JSONString = NewType("JSONString", object)
GenericScalar = NewType("GenericScalar", object)
BigInt = NewType("BigInt", int)


def _big_int(value: Any) -> int:
    return int(value)


SCALAR_MAP = {
    JSONString: strawberry.scalar(
        name="JSONString",
        description="Allows use of a JSON String for input / output from the GraphQL schema.",
        serialize=lambda value: json.dumps(value),
        parse_value=lambda value: json.loads(value),
    ),
    GenericScalar: strawberry.scalar(
        name="GenericScalar",
        description="The `GenericScalar` scalar type represents a generic GraphQL scalar value.",
        serialize=lambda value: value,
        parse_value=lambda value: value,
    ),
    BigInt: strawberry.scalar(
        name="BigInt",
        description="Integers that can exceed the 32-bit range of `Int`.",
        serialize=_big_int,
        parse_value=_big_int,
    ),
}
