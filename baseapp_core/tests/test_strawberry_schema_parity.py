"""Everything the Strawberry schema defines must match the Graphene schema.

Mismatches (types, nullability, arguments, enum values) always fail. Missing fields, types and
interfaces only mean "not ported yet" until STRAWBERRY_SCHEMA_COMPLETE is set; then they fail too.
Run `manage.py strawberry_parity --missing` for the remaining list.
"""

import os

from baseapp_core.strawberry.parity import SchemaDiff, compare_schemas, missing_types


def _schemas() -> tuple:
    from testproject.graphql import schema as graphene_schema
    from testproject.strawberry_schema import schema as strawberry_schema

    return graphene_schema.graphql_schema, strawberry_schema._schema


def _is_incomplete(diff: SchemaDiff) -> bool:
    if diff.kind == "missing field":
        return True
    if diff.kind == "interfaces":
        return set(diff.strawberry.split(", ")) <= set(diff.graphene.split(", "))
    return False


def _is_accepted(diff: SchemaDiff) -> bool:
    # DjangoDebug has no Strawberry equivalent and no frontend usage.
    return diff.kind == "missing field" and diff.path.endswith("._debug")


def test_ported_types_match_graphene() -> None:
    graphene, strawberry = _schemas()
    diffs = [d for d in compare_schemas(graphene, strawberry) if not _is_accepted(d)]
    mismatches = [str(d) for d in diffs if not _is_incomplete(d)]
    assert mismatches == [], "\n".join(mismatches)


def test_schema_is_complete_when_required() -> None:
    if not os.environ.get("STRAWBERRY_SCHEMA_COMPLETE"):
        return
    graphene, strawberry = _schemas()
    incomplete = [
        str(d)
        for d in compare_schemas(graphene, strawberry)
        if not _is_accepted(d) and _is_incomplete(d)
    ]
    missing = [t for t in missing_types(graphene, strawberry) if not t.startswith("DjangoDebug")]
    assert incomplete + missing == [], "\n".join(incomplete + missing)
