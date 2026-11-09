import logging

import pytest
import swapper
from graphql import GraphQLError, build_schema

from baseapp_core.strawberry.extensions import log_unexpected_errors
from baseapp_core.strawberry.parity import SchemaDiff, compare_schemas
from baseapp_core.strawberry.registry import (
    ModelLazyType,
    StrawberryTypeRegistry,
    type_for_model,
    type_registry,
)

OLD_SDL = """
    interface Node { id: ID! }
    enum Status { A_1 A_2 }
    input ToggleInput { id: ID! clientMutationId: String }
    type Thing implements Node {
        id: ID!
        name: String
        count(first: Int, offset: Int): Int
        gone: String
    }
    type Query { thing(id: ID!): Thing status: Status kind: String }
"""

NEW_SDL = """
    interface Node { id: ID! }
    enum Status { A_1 ACTIVE }
    input ToggleInput { id: ID! }
    type Thing {
        id: ID!
        name: String!
        count(first: Int): Int
        extra: Int
    }
    type Brand { id: ID! }
    union Kind = Thing | Brand
    type Query { thing(id: ID!): Thing status: Status kind: Kind }
"""


def test_compare_schemas_reports_every_contract_change() -> None:
    diffs = compare_schemas(build_schema(OLD_SDL), build_schema(NEW_SDL))

    assert {(d.path, d.kind) for d in diffs} == {
        ("Brand", "extra type"),
        ("Kind", "extra type"),
        ("Query.kind", "field type"),
        ("Status", "enum values"),
        ("Thing", "interfaces"),
        ("Thing.name", "field type"),
        ("Thing.count(offset)", "argument"),
        ("Thing.extra", "extra field"),
        ("Thing.gone", "missing field"),
        ("ToggleInput.clientMutationId", "missing field"),
    }
    assert diffs == sorted(diffs)


def test_compare_schemas_identical_and_kind_change() -> None:
    assert compare_schemas(build_schema(OLD_SDL), build_schema(OLD_SDL)) == []

    old = build_schema("type Query { a: A } type A { x: Int }")
    new = build_schema("type Query { a: A } interface A { x: Int }")
    assert compare_schemas(old, new) == [
        SchemaDiff("A", "kind", "GraphQLObjectType", "GraphQLInterfaceType")
    ]
    assert "expected=GraphQLObjectType" in str(compare_schemas(old, new)[0])


def test_registry_last_registration_wins_and_resolves_lazily() -> None:
    Profile = swapper.load_model("baseapp_profiles", "Profile")
    registry = StrawberryTypeRegistry()
    assert registry.get_type_for_model(Profile) is None

    class Base:
        pass

    class Override:
        pass

    registry.register(Profile, Base)
    registry.register(Profile, Override)
    assert registry.get_type_for_model(Profile) is Override


def test_type_for_model_uses_global_registry() -> None:
    Block = swapper.load_model("baseapp_blocks", "Block")
    from baseapp_blocks.strawberry.types import BlockType

    lazy = type_for_model(Block)
    assert isinstance(lazy, ModelLazyType)
    assert lazy.type_name == "Block"
    assert lazy.resolve_type() is type_registry.get_type_for_model(Block) is BlockType


def test_type_for_unregistered_model_raises() -> None:
    from django.contrib.contenttypes.models import ContentType

    with pytest.raises(LookupError):
        type_for_model(ContentType).resolve_type()


def test_log_unexpected_errors_skips_client_errors(caplog) -> None:
    unexpected = GraphQLError("boom", original_error=ValueError("boom"))
    client_error = GraphQLError("nope", original_error=GraphQLError("nope"))
    plain = GraphQLError("syntax")

    with caplog.at_level(logging.ERROR):
        log_unexpected_errors([unexpected, client_error, plain])

    assert [r.getMessage() for r in caplog.records] == ["boom"]
