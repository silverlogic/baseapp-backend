# Graphene → Strawberry migration plan (BaseApp stack)

Status: proposal, backed by a proof of concept on branch `feature/strawberry-poc` of `baseapp-backend`.

## 0. Status of the full port

Every package in `baseapp-backend` now has a Strawberry port next to its Graphene code, served
at `/graphql/strawberry`. Graphene still serves `/graphql` unchanged. How the port is built:

- **Schema parity gate.** `manage.py strawberry_parity` diffs the two schemas;
  `baseapp_core/tests/test_strawberry_schema_parity.py` fails on any mismatch in ported types.
  Setting `STRAWBERRY_SCHEMA_COMPLETE=1` also fails on anything not ported.
- **Behaviour gate.** `GRAPHQL_TEST_ENDPOINT=/graphql/strawberry` runs every existing GraphQL
  test against Strawberry. The same suite then proves both implementations.
- **Relations like `fields = "__all__"`.** `django_type(..., relations=...)` exposes model
  relations to other registered types when the schema is built, with Graphene's names,
  nullability and FilterSet arguments. No package declares fields for another package's models.
- **Mutations delegate to the Graphene logic.** Strawberry declares the input and payload types;
  `graphene_relay_mutation` runs the Graphene class's `mutate_and_get_payload` and maps the
  result. Both endpoints share one implementation while they coexist. Several resolvers also
  reuse the Graphene types' plain helper methods for the same reason.
- **Subscriptions are bridged.** Every Graphene `Subscription.broadcast` also publishes to a
  Strawberry channel group, so publishers are not touched until Graphene goes away.
- **Authentication mirrors Graphene.** The Strawberry view uses the DRF authentication classes
  listed in `GRAPHENE["MIDDLEWARE"]` (or `STRAWBERRY_AUTHENTICATION_CLASSES`).

What removing Graphene then involves, mechanically:

1. Move each Graphene mutation's `mutate_and_get_payload` body and the resolver helpers the
   Strawberry code reuses into Graphene-free modules, and point the Strawberry code there.
2. Replace each `Subscription.broadcast(group=G, payload=P)` call with
   `broadcast(subscription_group("<Name>", G), P)` and delete the bridge.
3. Set `STRAWBERRY_AUTHENTICATION_CLASSES` explicitly, drop the Graphene branches of the
   hashids strategies, and delete every `<package>/graphql/` module and the Graphene settings.
4. Serve Strawberry at `/graphql`, then unpin Strawberry and move to graphql-core 3.3.

## 1. Recommendation

Migrate, incrementally. Strawberry (`strawberry-graphql` + `strawberry-graphql-django`) can carry
every BaseApp GraphQL feature, including the query optimizations, **with a byte-compatible wire
contract**, so the frontend does not need to change. Run both schemas side by side
(`/graphql` = Graphene, `/graphql/strawberry` = Strawberry), port package by package behind two
automated gates, then switch the endpoint per project and delete Graphene.

The two gates, both already working in the POC:

1. **Schema parity** — `baseapp_core.strawberry.parity.compare_schemas` diffs every type the
   Strawberry schema defines against the Graphene schema (field types, nullability, arguments,
   interfaces, enum values). A package is "ported" when its diff is empty or every remaining line is
   an explicitly accepted exception.
2. **Behaviour + query-count parity** — `baseapp_core.strawberry.testing.run_on_both` sends the same
   document to both endpoints and the test asserts identical JSON and
   `strawberry queries <= graphene queries`, plus "same count for 3 rows and 20 rows".

## 2. Why now

- The stack is pinned to `graphql-core<3.3` by `graphene 3.4.3`; current Strawberry already
  requires `graphql-core 3.3`. Staying on Graphene means staying on an old `graphql-core`.
- Our performance layer depends on `graphene-django-query-optimizer` plus local monkey-patches of its compiler (`baseapp_core/graphql/optimizer.py`); a dead second
  optimizer (`graphene-django-optimizer`) is still mixed into 8 package types and 6 template types.
- Subscriptions run on our own fork, `baseapp-django-channels-graphql-ws==1.0.0rc9`.
- About half the connection fields (`DjangoFilterConnectionField`) silently skip the optimizer
  today. In Strawberry every connection goes through the same optimizer, so the migration removes
  that whole class of N+1 bug.

## 3. What the proof of concept shows

Scope: `baseapp_core` infrastructure plus the `baseapp_blocks` slice (the `BlocksInterface` shared
interface with field-level optimizer hints, the `Block` type, the `blockToggle` mutation) and the
part of `Profile` that implements it. Everything runs in the same process as Graphene.

### Results

Every scenario sends the same document to both endpoints. "Same response" means byte-equal JSON
(ids included), except the mutation, which is compared after normalizing freshly created ids.

| Scenario | Same response | SQL queries, Graphene | SQL queries, Strawberry |
|---|---|---|---|
| `node(id)` → `blockersCount` / `blockingCount`, 3 blocks | yes | 6 | 6 |
| same, 20 blocks | yes | 6 | 6 |
| same, permission denied (counts are `null`) | yes | 9 | 9 |
| `blocking.edges.node.target.blockersCount`, 3 blocks | yes | 9 | 9 |
| same, 20 blocks (no N+1) | yes | 9 | 9 |
| `blockers(first: 2)` with `totalCount`, `edgeCount`, `pageInfo`, cursors | yes | 9 | 9 |
| `node(id)` on `Block`, public ids | yes | 9 | 9 |
| `node(id)` on `Block`, legacy base64 ids | yes | 5 | 4 |
| `node(id)` on `Block` without permission → `null` | yes | – | – |
| empty / unknown id → `null` | yes | – | – |
| `Authorization: Token` + `Current-Profile` header, `isBlockedByMe` | yes | 12 | 12 |
| `blockToggle` anonymous → `authentication required` error | yes | – | – |
| `blockToggle` create + delete, `clientMutationId`, `errors` | yes (normalized) | – | – |
| Schema diff of every ported type | only the accepted deltas (section 5) | | |
| WebSocket: `connectionParams` JWT / `Refresh` / `Current-Profile`, broadcast delivered over graphql-transport-ws | yes | | |

The existing Graphene test suites of `baseapp_core`, `baseapp_blocks` and `baseapp_profiles` still
pass with the Strawberry endpoint mounted next to Graphene.

### What the parity runs caught

These are the lessons that shape the migration guide. The first three were caught by the parity
tests, not by reading code, which is the argument for making the gates mandatory.

1. **A hint must not capture the model.** The `id` field object is shared by every type that
   implements `Node`, so a hint bound to one model at decoration time annotated `Block` rows with
   `Profile`'s public-id subquery. The result was legacy ids, and it could just as well have been
   *wrong* ids. Hints now read the model from the GraphQL type that owns the field at query time
   (`model_from_info`).
2. **Two foreign keys to the parent model.** When `Block` is listed under a `Profile`, Strawberry
   Django adds the FK back to the parent to `only()`, but it stops at the first FK to that model
   (`actor`), so `target_id` was refetched once per row. Fix: `django_type(Block,
   only=["actor_id", "target_id"])`. The same applies to `Follow`, `Report` and any
   actor/target model.
3. **Permission backends read deferred columns.** `has_perm` on `Profile` reads `status` and
   `owner_id`; deferred, each read is a `refresh_from_db`. Fix: `django_type(Profile,
   only=[...])`. This is compose-a-block's pattern A; it now lives in the type declaration.
4. **Field type mapping.** graphene-django converts model fields by `isinstance`, Strawberry Django
   by exact class, so subclasses such as django-model-utils' `AutoCreatedField` must be registered.
5. **Sync resolvers in async contexts.** Over WebSockets the resolvers run on the event loop, and
   Django raises `SynchronousOnlyOperation` on any ORM call there. `strawberry_django.field`
   resolvers are wrapped in `django_resolver`, which hops to a thread; plain `strawberry.field`
   resolvers (such as `Node.id`, which may query `DocumentId`) are not. The Graphene consumer hid
   this with its `threadpool_for_sync_resolvers` middleware.

### Code

| Piece | Path | Replaces |
|---|---|---|
| `Node` interface, `node` root field, id decoding | `baseapp_core/strawberry/relay.py` | `baseapp_core.graphql.relay` + the Graphene halves of the hashids strategies |
| `django_type` decorator, public-id optimizer hint | `baseapp_core/strawberry/types.py` | `baseapp_core.graphql.DjangoObjectType` and its `pre_optimization_hook` walker |
| Model → type registry, `type_for_model` lazy refs | `baseapp_core/strawberry/registry.py` | Graphene registry, `get_object_type_for_model` |
| `CountedConnection`, nullable `Edge` | `baseapp_core/strawberry/connections.py` | `CountedConnection` |
| `relay_mutation`, `RelayMutationInput/Payload`, `ErrorType`, `IsAuthenticated` | `baseapp_core/strawberry/mutations.py` | `RelayMutation`, `Errors`, `login_required` |
| View: `info.context` is the request, Token/JWT auth | `baseapp_core/strawberry/views.py` | `GraphQLView`, auth middlewares |
| Sentry + pghistory per operation, error logging | `baseapp_core/strawberry/extensions.py`, `schema.py` | `GraphQLView.execute_graphql_request`, `LogExceptionMiddleware` |
| WebSocket consumer, `broadcast`, `listen` | `baseapp_core/strawberry/subscriptions.py` | `baseapp_core/graphql/consumers.py`, `Subscription.broadcast` |
| Current-Profile header | `baseapp_profiles/strawberry/extensions.py` | `CurrentProfileMiddleware` (Graphene) |
| Plugin roots | `PackageSettings.strawberry_queries / strawberry_mutations / strawberry_types`, `GraphQLContributor.register_strawberry_shared_interfaces` | `graphql_queries` / `graphql_mutations`, `register_graphql_shared_interfaces` |
| Parity tooling | `baseapp_core/strawberry/parity.py`, `testing.py`, `baseapp_blocks/tests/test_strawberry_parity.py` | new |

Key design choices:

- **`info.context` is the Django request**, exactly as in Graphene. The 218 `info.context.user`
  references and every shared service keep working unchanged.
- **Ids are produced and parsed by the existing hashids strategies** (public id / pk / legacy
  base64). Strawberry's own `GlobalID` is not used, so ids are identical on both endpoints.
- **The public-id annotation is a field-level hint on `id`.** It is applied at every nesting level by
  Strawberry's optimizer, which removes the recursive walker and the "remember to append `id` to
  `only_fields`" trap from `compose-a-block`.
- **Shared interfaces are plain base classes** resolved through the same name-based registry, so a
  package can still add fields to another package's type without importing it.

## 4. Feature mapping

| Graphene feature (count in `baseapp-backend`) | Strawberry equivalent | Status |
|---|---|---|
| `DjangoObjectType` subclasses (21) | `@django_type(Model)` | POC |
| Relay `Node`, `node(id:)`, hashids ids | custom `Node` + `node_field()` | POC |
| `get_node` permission overrides (16) | same classmethod contract on `Node` | POC |
| `pre_optimization_hook` (7) | type hints `django_type(Model, only=, select_related=, prefetch_related=, annotate=)`; callables for dynamic `Prefetch`/`GenericPrefetch` | pattern A–C mechanical; D (GenericPrefetch via `DocumentId`) to prove in phase 1 |
| field `optimizer_hook` (5) | `strawberry_django.field(annotate=..., prefetch_related=...)` | POC (`blockersCount`, `blockingCount`) |
| interface `Meta.model` workaround | not needed: the optimizer expands `... on Interface` against the concrete type | POC |
| `query_optimizer.DjangoConnectionField` (11) | `strawberry_django.connection(CountedConnection[T] \| None)` | POC |
| `DjangoFilterConnectionField` + `FilterSet` (19 fields, 15 filtersets) | connection + a `FilterSet` adapter that exposes the filterset fields as flat arguments and applies the `FilterSet` in the resolver (keeps the SDL and reuses `filters.py`) | to build (phase 0) |
| `RelayMutation` (36) | `@relay_mutation` | POC |
| `SerializerMutation` (5) | `serializer_mutation` helper: DRF validation → `errors: [ErrorType]` | to build |
| `login_required` (41) | `relay_mutation(login_required=True)` / `IsAuthenticated` | POC |
| `CountedConnection` (`totalCount`, `edgeCount`) | `CountedConnection` (window-function `totalCount`) | POC |
| `graphene.Enum` and auto choice enums (11) | explicit `strawberry.enum` with the same type and value names (e.g. `ProfilesProfileStatusChoices { A_1, A_2 }`) | to build |
| `ThumbnailField` (9) | field factory with `width`/`height` args, same cache keys | to build |
| Custom scalars: `JSONString`, `GenericScalar`, `Decimal`, `BigInt`, geojson, `Upload` | `strawberry.scalar` definitions with the same names | to build |
| model-utils / phonenumber / translated fields | `field_type_map` registrations (model-utils done) | partial |
| `_debug` / `DjangoDebug` (41 schema fields) | dropped; Strawberry Django has a debug-toolbar integration. No frontend usage | decision needed |
| `NestedConnectionInfoProxy` (comments → comments) | expected to be unnecessary: each nested connection is optimized with its own `info` | prove in phase 1 |
| Subscriptions (5) on `channels_graphql_ws` | `baseapp_core.strawberry.subscriptions`: `GraphQLWSConsumer` (graphql-transport-ws, which the frontend's `graphql-ws` 6 client speaks) with the same `connectionParams` auth; `broadcast(group, payload)` replaces `Subscription.broadcast` (11 call sites); resolvers are async generators over `listen(info, groups)` | infrastructure POC; the 5 subscriptions still to port |
| Uploads | the frontend does **not** use the multipart spec: it posts `query`, `variables` and files keyed by name, and mutations read `info.context.FILES`. The view needs a parser for that form; since `info.context` is the request, the mutations keep working | to build |
| `GRAPHENE__MIDDLEWARE` plugin slot | `STRAWBERRY__EXTENSIONS` slot of `SchemaExtension`s | to build |
| `graphql_schema` / `SCHEMA_OUTPUT` | `strawberry export-schema`, plus a CI snapshot check (none exists today) | to build |

## 5. Contract with the frontend

The frontend (`baseapp-frontend` + template) compiles 124 Relay documents against a committed
`schema.graphql`, downloaded by hand from the backend. It depends on:

- `errors { field messages }` on 27 mutation documents (`setFormRelayErrors`, `getMutationErrorMessage`);
- `clientMutationId` (4 call sites), `totalCount` (5 documents);
- `node(id:)` + the `Node` interface (17 `@refetchable` fragments);
- `Authorization` / `Current-Profile` / `Accept-Language` headers on HTTP;
- `Authorization` / `Refresh` / `Current-Profile` in the WebSocket `connectionParams`;
- the non-spec upload form described above.

All of these are preserved by design. Accepted SDL deltas so far:

| Delta | Why it is safe |
|---|---|
| `offset` argument removed from connections | no frontend document uses it |
| interfaces that inherit `Node` declare `implements Node` | additive |
| `_debug` fields removed | no frontend document uses them |

Verification for the frontend is mechanical: download the schema from `/graphql/strawberry`, diff it
against the committed `schema.graphql`, and run `relay-compiler`. The expected outcome is "no change
in `__generated__`".

## 6. Phases

### Phase 0 — Foundations (`baseapp_core`)

- Harden `baseapp_core.strawberry` from the POC.
- Build the missing pieces from section 4: `FilterSet` adapter, `serializer_mutation`, enums and
  scalars, `ThumbnailField`, upload parsing, `STRAWBERRY__EXTENSIONS` slot.
- Split the hashids strategies into a framework-agnostic "global id → (model, pk)" step plus thin
  Graphene/Strawberry adapters (today `get_node` resolution reads the Graphene schema).
- **Subscriptions**: the transport, auth and broadcast pieces are proven in the POC. Port
  `onNotificationChange` end to end, turn broadcast payloads into ids (they cross the channel
  layer), and drive it with the frontend's `graphql-ws` client against a QA stack.
- Make every custom resolver async-safe (lesson 5), e.g. a `django_type` default that wraps plain
  resolvers.
- CI: schema export + snapshot diff in both template and submodule; parity tests run in the
  normal pytest job.

### Phase 1 — Pilots that retire the risks

1. `baseapp_auth` (`User`) and `baseapp_profiles` in full — the most connected type, plus its
   currently unoptimized `DjangoFilterConnectionField`s.
2. `baseapp_comments` — nested same-type connections (`NestedConnectionInfoProxy` today).
3. `baseapp_follows` — `GenericPrefetch` through `DocumentId` (pattern D).
4. `baseapp_chats` — subscriptions + uploads + the largest GraphQL module (1.9k lines).

### Phase 2 — Remaining packages

In dependency order, one PR per package, each with a zero (or accepted) schema diff and every
existing query-count test re-run against `/graphql/strawberry`:
`pages`, `files`, `reactions`, `blocks` (finish), `reports`, `ratings`, `mentions`,
`notifications`, `organizations`, `content_feed`, `activity_log`, `api_key`.

Rule while both schemas exist: once a package is ported, new GraphQL work for it lands in Strawberry
and is mirrored to Graphene only if the template still serves Graphene; the parity test enforces it.

### Phase 3 — Template and frontend validation

- Port the 11 thin `apps/*/graphql` overrides (125 lines) to `@django_type` re-registrations, and
  the 7 `get_graphql_object_type()` overrides to the type registry.
- Add `apps/strawberry_schema.py`, the URL, and the ASGI WebSocket route.
- Point the frontend env (`NEXT_PUBLIC_RELAY_ENDPOINT`, `NEXT_PUBLIC_WS_RELAY_ENDPOINT`) at the
  Strawberry endpoints on a QA stack, diff the downloaded schema, run unit + Playwright suites.
  No frontend code change is expected.

### Phase 4 — Cutover and cleanup

- Serve Strawberry at `/graphql` (setting-controlled), keep Graphene at `/graphql/legacy` for one
  release, watch Sentry and query counts.
- Remove `graphene`, `graphene-django`, both optimizers, `graphene-file-upload`,
  `baseapp-django-channels-graphql-ws`, the Graphene halves of the hashids strategies, and
  `baseapp_core/graphql/optimizer.py`.
- Unpin Strawberry to current releases and move to `graphql-core 3.3`.
- Rewrite `compose-a-block` sections 7–11 and the GraphQL rules in `AGENTS.md` / convention skills.

### Phase 5 — Client projects

Projects forked from the template carry their own Graphene code in `apps/`. Ship a migration guide
(type → `@django_type`, mutation → `@relay_mutation`, hook → hints) and the parity helpers so each
project can port and verify at its own pace while BaseApp still serves both schemas.

## 7. Effort (rough)

| Phase | Size | Notes |
|---|---|---|
| 0 | 2–3 dev-weeks | FilterSet adapter, serializer mutations, scalars, uploads, first real subscription |
| 1 | 2–3 dev-weeks | profiles + comments + follows + chats |
| 2 | 3–4 dev-weeks | parallelizable across devs after phase 1 |
| 3 | 1 dev-week | template + frontend validation on QA |
| 4 | 1 dev-week | plus one release of dual serving |

About 9–12 dev-weeks in total. Graphene code today is ~9k lines in 70 non-test files in
`baseapp-backend`, 125 lines in the template, and 114 test files touch GraphQL.

## 8. Risks

- **Version pin during coexistence.** Strawberry `0.327.x` and Strawberry Django `0.91.x` are the
  last releases on `graphql-core 3.2`. We forgo newer fixes until Graphene is removed.
- **Two schemas drifting.** Mitigated by the parity test and the "ported package lands in
  Strawberry" rule.
- **Optimizer differences.** Strawberry Django also defers unselected columns, so
  "resolver reads an unexposed column" (compose-a-block pattern A) still needs an `only=` hint. A
  `get_queryset` classmethod on a type turns every FK to it into a separate prefetch query. The
  query-count gate catches both.
- **Subscriptions** are a rewrite of the server side, not a port. Transport and auth are proven;
  the publish side (11 `broadcast` call sites) and async-safety of payload resolvers remain.
- **Client forks** with heavy custom Graphene code; mitigated by phase 5 and dual serving.

## 9. Decisions needed

1. Accept the SDL deltas in section 5 (`offset`, `implements Node`, `_debug`).
2. Adopt the "ported packages land in Strawberry" rule for the migration window.
3. Keep the Relay mutation shape (`input`, `clientMutationId`, `errors`) long term, or plan a later,
   frontend-coordinated move to Strawberry-native mutations.

## Running the POC

```bash
# from baseapp-backend/
docker compose run --rm web uv run pytest -s \
  baseapp_blocks/tests/test_strawberry_parity.py \
  baseapp_core/tests/test_strawberry_core.py \
  baseapp_core/tests/test_strawberry_subscriptions.py
```

GraphiQL for the Strawberry schema is served at `/graphql/strawberry` next to Graphene's `/graphql`.
