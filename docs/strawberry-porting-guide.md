# Porting a package from Graphene to Strawberry

How to port one `baseapp_*` package's GraphQL layer while Graphene keeps serving `/graphql`.
Reference implementations: `baseapp_auth/strawberry/`, `baseapp_profiles/strawberry/`,
`baseapp_blocks/strawberry/`. Core helpers: `baseapp_core/strawberry/`.

## Definition of done for a package

1. `manage.py strawberry_parity --type <EachType>` shows no mismatch for the package's types
   (missing fields that belong to *other, unported* packages are fine).
2. The package's tests pass on both endpoints:
   `pytest <pkg>/tests` and `GRAPHQL_TEST_ENDPOINT=/graphql/strawberry pytest <pkg>/tests`.
   Strawberry may use *fewer* queries than an exact-count assertion expects; report those.
   Failures caused by other unported packages ("Cannot query field X", "Unknown type Y") are fine.
3. `baseapp_core/tests/test_strawberry_schema_parity.py` passes.
4. Graphene code is untouched (except when a test proves a shared bug).

## Layout

```
<pkg>/strawberry/__init__.py    lazy getters for shared interfaces (no strawberry imports at top)
<pkg>/strawberry/interfaces.py  shared interfaces
<pkg>/strawberry/types.py       model types
<pkg>/strawberry/queries.py     root query fields  -> plugin.py strawberry_queries
<pkg>/strawberry/mutations.py   inputs, payloads   -> plugin.py strawberry_mutations
<pkg>/strawberry/subscriptions.py                  -> plugin.py strawberry_subscriptions
```

`plugin.py`: add `strawberry_queries=[...]`, `strawberry_mutations=[...]`,
`strawberry_subscriptions=[...]` and `strawberry_types=["<pkg>.strawberry.types.XType", ...]`
(every module defining types must be listed or imported by one that is).

`apps.py` (shared interfaces): mirror `register_graphql_shared_interfaces`:

```python
def register_strawberry_shared_interfaces(self, registry) -> None:
    from .strawberry import get_comments_interface   # lazy getter, imports on call
    registry.register("CommentsInterface", get_comments_interface)
```

## Model types

```python
@django_type(Model, filterset_class=XFilter, relations="__all__", only=["col_read_by_perms"])
class XType(AbstractXType, *strawberry_shared_interfaces.get("AInterface", "BInterface"), Node):
    ...
```

- The GraphQL name defaults to the model name. `Node` must be the last base.
- Use an abstract base `@strawberry_django.type(Model, name="AbstractX")` holding the fields when
  projects override the type (Profile, Reaction, Rate, Report, ReportType, File, Page, and the
  template's `apps/*/graphql` types). Projects subclass it and re-decorate with `django_type`; the
  last registration wins.
- `filterset_class`: the Graphene `Meta.filterset_class`. Connections derived from relations to this
  type use it for their arguments.
- `relations`: Graphene `fields = "__all__"` → `relations="__all__"`; an explicit Graphene `fields`
  list → the relation names in it. Relations to other registered types are added automatically at
  schema build with Graphene's naming and nullability (`owner: User!`, `activitylogSet:
  ActivityLogConnection!`, reverse one-to-one nullable). Never declare those by hand.
- Scalars: `strawberry.auto` (check nullability against the SDL; override with an explicit
  annotation when they differ). `pk: int | None = strawberry_django.field()` where the SDL has `pk`.
- Choice fields: `choices_enum(Model, "field")` reproduces graphene-django's
  `<App><Model><Field>Choices`; `enum_from_choices(TextChoicesCls, "Name")` for
  `graphene.Enum.from_enum`. Use the same enum object everywhere for a given GraphQL name.
- `ThumbnailField()` → `thumbnail_field("model_attr")` (or a callable on the instance).
- `JSONString`, `GenericScalar`, `BigInt`: `baseapp_core.strawberry.scalars`. `Date`, `DateTime`,
  `Decimal`, `UUID`, `Upload` are Strawberry built-ins with the same names.
- `get_node` → `@classmethod def get_node(cls, info, pk)`; call `super().get_node(info, pk)`, then
  check permissions.
- `get_queryset` → `@classmethod def get_queryset(cls, queryset, info, **kwargs)`. It applies to
  root lists, node lookups and to-many connections, not to to-one traversals (same as Graphene).

## References between types

- `type_for_model(Model)` returns a lazy reference resolved through the registry (respects project
  overrides). Use it for every cross-type reference.
- **Never pass a lazy type as `graphql_type=` to `strawberry_django.field`** — it resolves at class
  creation and crashes. Use a plain annotation (`target: ProfileLazyType | None`) or, for resolver
  fields, `@strawberry.field(graphql_type=Optional[Lazy])`.
- Strawberry Django fields with resolvers are async-safe; plain `strawberry.field` resolvers are not
  (matters for subscription payloads).

## Optimization (replaces `pre_optimization_hook` / `optimizer_hook`)

- Columns a resolver or permission check reads but GraphQL doesn't expose → `only=[...]` on the type
  (or on the field). Deferred columns are refetched per row otherwise.
- Models with two FKs to the same parent (actor/target): add both `_id` columns to `only=`.
- Annotations that a field needs → field hint: `strawberry_django.field(annotate={"_x": lambda info:
  expr(model_from_info(info))})`. On shared interfaces the model comes from `model_from_info(info)`.
- Unconditional `annotate_queryset` calls in a hook → move them to the fields that read them.
- Virtual relations through `DocumentId` → `prefetch_related=lambda info: Prefetch(...)` on the field.
- `skip_ast_walker`, `NestedConnectionInfoProxy`, `gql_optimizer`: not needed; nested connections
  are optimized per field.
- Relay `id` gets the public-id annotation automatically.

## Connections

```python
@connection(CountedConnection[XLazy] | None, filterset_class=XFilter)
def items(self, info: Info) -> Iterable[Model]: ...
```

- Graphene `DjangoFilterConnectionField` / `DjangoConnectionField` declared on a type or root →
  nullable `CountedConnection[T] | None` (relation-derived ones are generated, non-null).
- Arguments `offset/before/after/first/last` + FilterSet arguments are added automatically.
  `default_first=10` reproduces `first: Int = 10`; `filter_overrides={"name": Type}` fixes a type.
- A root connection without resolver lists the type's model through its `get_queryset`.
- Return querysets, never lists.

## Shared interfaces

```python
@strawberry.interface(name="CommentsInterface")
class CommentsInterface(Node):
    ...
```

Fields on interfaces are copied into implementing types. Register through `apps.py` with a lazy
getter (above); consumers list names in `strawberry_shared_interfaces.get(...)`.

## Queries

- `Node.Field(XType)` → `x = typed_node_field(XLazy)`.
- `graphene.Field(T, resolver)` → `@strawberry.field(graphql_type=Optional[XLazy])` with a method.

## Mutations

Declare input and payload types matching the SDL and delegate the logic to the Graphene class:

```python
@strawberry.input(name="XCreateInput")
class XCreateInput(RelayMutationInput):
    target_object_id: strawberry.ID
    body: str | None = UNSET        # optional without default in SDL -> UNSET (stays omitted)
    role: RolesEnum | None = None   # SDL shows "= null" -> None

@strawberry.type(name="XCreatePayload")
class XCreatePayload(RelayMutationPayload):
    x: Edge[XLazy] | None = None    # graphene ..._meta.connection.Edge
    other: XLazy | None = None

@strawberry.type
class XMutations:
    x_create = graphene_relay_mutation(graphene_mutations.XCreate, XCreateInput, XCreatePayload)
```

`graphene_relay_mutation` passes `**input` exactly as Graphene would (snake_case, omitted fields
absent, Django `Choices` members kept, nested inputs as attribute dicts) and maps the returned
Graphene payload (edges, `ErrorType`s, instances) onto the Strawberry payload. `info.context` is
the request, so `login_required`, `info.context.user` and `info.context.FILES` keep working.

## Subscriptions

Async generators over `baseapp_core.strawberry.subscriptions.listen(info, groups)`; publishers call
`broadcast(group, payload)` (payloads cross the channel layer: send ids, re-fetch with
`database_sync_to_async`). Test with `strawberry.channels.testing.GraphQLWebsocketCommunicator`
(see `baseapp_core/tests/test_strawberry_subscriptions.py`).

## Running checks

From `baseapp-backend/`, with a compose project name of your own:

```bash
docker compose run --rm -e DJANGO_SETTINGS_MODULE=testproject.settings web \
  uv run python manage.py strawberry_parity --type Comment --type CommentsInterface
docker compose run --rm -e GRAPHQL_TEST_ENDPOINT=/graphql/strawberry web \
  uv run pytest baseapp_comments/tests -q --reuse-db
```
