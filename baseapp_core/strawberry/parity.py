"""Schema parity between the Graphene schema and the Strawberry schema.

During the migration the frontend keeps compiling against the Graphene SDL, so every type ported
to Strawberry must expose the same contract. `compare_schemas` lists every difference for the
types present in the Strawberry schema; a parity test pins the accepted ones.
"""

from dataclasses import dataclass

from graphql import (
    GraphQLEnumType,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLNamedType,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLSchema,
    GraphQLUnionType,
    is_introspection_type,
    is_specified_scalar_type,
)

_KINDS = (
    GraphQLObjectType,
    GraphQLInterfaceType,
    GraphQLInputObjectType,
    GraphQLEnumType,
    GraphQLUnionType,
    GraphQLScalarType,
)


def _kind(type_: GraphQLNamedType) -> str:
    return next(k.__name__ for k in _KINDS if isinstance(type_, k))


@dataclass(frozen=True, order=True)
class SchemaDiff:
    path: str
    kind: str
    graphene: str
    strawberry: str

    def __str__(self) -> str:
        return f"{self.path}: {self.kind} (graphene={self.graphene}, strawberry={self.strawberry})"


def _fields_with_args(type_: GraphQLNamedType) -> dict[str, tuple[str, dict[str, str]]]:
    if isinstance(type_, GraphQLInputObjectType):
        return {name: (str(f.type), {}) for name, f in type_.fields.items()}
    return {
        name: (str(f.type), {arg: str(a.type) for arg, a in f.args.items()})
        for name, f in type_.fields.items()
    }


def _compare_type(name: str, old: GraphQLNamedType, new: GraphQLNamedType) -> list[SchemaDiff]:
    diffs: list[SchemaDiff] = []
    if _kind(old) != _kind(new):
        return [SchemaDiff(name, "kind", _kind(old), _kind(new))]

    if isinstance(new, GraphQLEnumType):
        old_values, new_values = set(old.values), set(new.values)
        if old_values != new_values:
            diffs.append(
                SchemaDiff(name, "enum values", str(sorted(old_values)), str(sorted(new_values)))
            )
        return diffs

    if isinstance(new, (GraphQLObjectType, GraphQLInterfaceType)):
        old_ifaces = sorted(i.name for i in old.interfaces)
        new_ifaces = sorted(i.name for i in new.interfaces)
        if isinstance(new, GraphQLInterfaceType) and "Node" not in old_ifaces:
            # Strawberry interfaces that inherit Node declare it: additive, harmless for clients.
            new_ifaces = [i for i in new_ifaces if i != "Node"]
        if old_ifaces != new_ifaces:
            diffs.append(
                SchemaDiff(name, "interfaces", ", ".join(old_ifaces), ", ".join(new_ifaces))
            )

    if not isinstance(new, (GraphQLObjectType, GraphQLInterfaceType, GraphQLInputObjectType)):
        return diffs

    old_fields, new_fields = _fields_with_args(old), _fields_with_args(new)
    for field_name, (new_type, new_args) in new_fields.items():
        path = f"{name}.{field_name}"
        if field_name not in old_fields:
            diffs.append(SchemaDiff(path, "extra field", "-", new_type))
            continue
        old_type, old_args = old_fields[field_name]
        if old_type != new_type:
            diffs.append(SchemaDiff(path, "field type", old_type, new_type))
        for arg in sorted(set(old_args) | set(new_args)):
            if old_args.get(arg) != new_args.get(arg):
                diffs.append(
                    SchemaDiff(
                        f"{path}({arg})", "argument", old_args.get(arg, "-"), new_args.get(arg, "-")
                    )
                )
    for field_name in old_fields.keys() - new_fields.keys():
        diffs.append(
            SchemaDiff(f"{name}.{field_name}", "missing field", old_fields[field_name][0], "-")
        )
    return diffs


def compare_schemas(
    graphene_schema: GraphQLSchema, strawberry_schema: GraphQLSchema
) -> list[SchemaDiff]:
    """Differences for every named type defined by the Strawberry schema (root types included)."""
    diffs: list[SchemaDiff] = []
    for name, new in strawberry_schema.type_map.items():
        if is_introspection_type(new) or is_specified_scalar_type(new):
            continue
        old = graphene_schema.type_map.get(name)
        if old is None:
            diffs.append(SchemaDiff(name, "extra type", "-", _kind(new)))
            continue
        diffs.extend(_compare_type(name, old, new))
    return sorted(diffs)


def missing_types(graphene_schema: GraphQLSchema, strawberry_schema: GraphQLSchema) -> list[str]:
    """Graphene types the Strawberry schema does not define yet."""
    return sorted(
        name
        for name, type_ in graphene_schema.type_map.items()
        if not is_introspection_type(type_)
        and not is_specified_scalar_type(type_)
        and name not in strawberry_schema.type_map
    )
