---
name: compose-a-block
version: 1.0.0
description: ALWAYS use this skill when creating, extending, or reviewing a reusable package ("block") inside the baseapp-backend monorepo, and whenever GraphQL query performance is in play anywhere in this repo. Trigger on requests like "add a new baseapp package for X", "scaffold baseapp_foo", "wire up a plugin", "register a shared service", "expose this via a GraphQL shared interface", "make this model swappable", "why is this query doing N+1", "this list endpoint is slow", "add a counter field without a query per row", "add an optimizer hint", "annotate this queryset", "the optimizer isn't picking up my prefetch", or "add a query-count regression test". Covers package scaffolding, plugin.py + PackageSettings, entry-point registration, AppConfig contributor mixins, swappable models and overridable Strawberry types, the DocumentId decoupling layer, shared services / Strawberry shared interfaces, and the full query-optimization stack (strawberry-django optimizer hints on types and fields, annotate_queryset, connection fields, query-count tests). The plugin-architecture half is for this repo only; the query-optimization half also applies to a consuming template's apps/ code, which uses the same `baseapp_core.strawberry` helpers and hits the same traps. Skip ONLY for package-authoring questions about a consuming template's apps/ directory, dependency bumps, and doc-only edits.
triggers:
  - create a new baseapp package
  - scaffold a block
  - register a plugin
  - add a shared service
  - make a model swappable
  - fix an N+1 query
  - optimize a GraphQL resolver
  - add a queryset annotation
config:
  service: web
  compose_file: docker-compose.yml
---

# compose-a-block

This skill covers authoring a reusable package — a *block* — inside the `baseapp-backend`
monorepo, and the query-optimization layer every block's GraphQL surface depends on.

Blocks are plugins. They are discovered through a setuptools entry point, contribute settings
declaratively, and wire runtime behaviour in `AppConfig.ready()`. No block imports another block
for runtime behaviour.

## Scope

The two halves of this skill have different reach.

**Sections 1–6 (plugin architecture) are for this repository only** — `baseapp/<name>/` or
`baseapp_<name>/`. A consuming template's `apps/` directory consumes blocks rather than defining
them, so plugin registration, swappable models, and the shared registries don't apply there; the
template ships its own `backend-conventions` and `backend-patterns` skills for that code.

**Sections 7–11 (query optimization) apply to any Strawberry code built on
`baseapp_core.strawberry`** (`django_type`, `connection`, `Node`) — including a consuming
template's `apps/`. Those types run under the same `DjangoOptimizerExtension` and hit the same
deferred-column and virtual-relation traps. Use these sections there, alongside the template's own
skills rather than instead of them.

Two companion skills still apply to everything here: `run-development-commands` for translating
intent into Docker Compose commands, and `ensure-test-coverage` for the 75% floor.

## How to use this skill

Each section below summarizes one area. When a task touches that area, read the corresponding
reference file before writing code — the references carry the real code, the file:line anchors,
and the anti-patterns.

If you are creating a package from scratch, read sections 1–3 in order; they are a single
sequence and skipping one leaves the package undiscoverable.

If you are chasing an N+1, start at section 7.

---

## Before you start

`baseapp_core/plugins/README.md` is the longest description of the architecture and is partly
stale. It says entry points live in a root `setup.cfg` (that file does not exist — they are in
`pyproject.toml`) and tells you to add `-e ./baseapp_yourpackage` to a `requirements.txt` (this is
one distribution managed by `uv`; there is nothing to install per package). Read it for the *why*;
take the *how* from this skill.

Strawberry patterns are catalogued in `docs/strawberry-porting-guide.md`; native examples are
`baseapp_blocks/strawberry/` and `baseapp_auth/strawberry/`. The core API lives in
`baseapp_core/strawberry/`.

---

## Sections

### 1. Package Scaffold
New packages go in `baseapp/<name>/` (the namespaced layout used by the two newest blocks), not
`baseapp_<name>/` at the root. `__init__.py` is empty; `apps.py` and `plugin.py` are mandatory;
`models.py`, `services.py`, `strawberry/`, `filters.py`, `permissions.py`, `signals.py`, `admin.py`, and `README.md`
are added as needed. Blocks with swappable models ship **no migrations** — the concrete models and
their migrations live in `testproject/`.

Read `references/package-scaffold.md` when: starting a new block, deciding which modules a block
needs, or checking whether an existing block is missing a conventional file.

---

### 2. Plugin Registration
`plugin.py` defines a `BaseAppPlugin` subclass returning a pydantic `PackageSettings`: installed
apps, slotted middleware/auth backends, extra Django settings, URL callbacks, Strawberry roots and
types (`strawberry_queries/mutations/subscriptions/types`), and declared package dependencies. Registration then touches `pyproject.toml` (entry
point + package-data), `MANIFEST.in`, and `testproject/settings.py`. Miss any one and the block
loads but contributes nothing.

Read `references/plugin-registration.md` when: adding a new block, adding a setting or URL to an
existing block, wiring GraphQL roots, or debugging a plugin that isn't contributing its settings.

---

### 3. AppConfig Wiring
`apps.py` declares `PackageConfig(BaseAppConfig, *Contributor)` with `default = True`. Runtime
registration happens through the contributor mixins — `ServicesContributor`,
`GraphQLContributor`, `SerializersContributor` — which `BaseAppConfig.ready()` dispatches by
`isinstance`. Override `ready()` only to connect signals, and always call `super().ready()` first.

Read `references/app-config-wiring.md` when: registering a shared service or GraphQL interface,
connecting signals, or debugging a registry that comes back empty at runtime.

---

### 4. Swappable Models
Concrete models in a block must be swappable so consuming projects can substitute their own.
Declare the model `abstract = True` with `swappable = swapper.swappable_setting(...)`, put the
GraphQL fields on an abstract `@strawberry_django.type(Model, name="AbstractX")` base registered by
`@django_type` (projects re-register their own; last registration wins), reference the type only
via `type_for_model(Model)`, and load the model everywhere else with `swapper.load_model(...)` at
module level. Optional cross-block fields are mixed in at class-definition time behind
`apps.is_installed(...)`.

Read `references/swappable-models.md` when: adding any concrete model to a block, referencing
another block's model, writing a migration that touches a swappable model, or wiring the concrete
counterpart in `testproject/`.

---

### 5. The DocumentId Layer
Blocks never foreign-key into each other's tables. `DocumentId` is a central
`(content_type, object_id, public_id)` registry; blocks attach to it via `DocumentIdMixin` (make
me documentable), `DocumentIdTargetMixin` (I point at a document), or
`DocumentIdUniqueTargetMixin` (I am a 1:1 sidecar for a document). This is also what makes the
relay-id optimization in section 7 possible.

Read `references/document-id.md` when: designing a block's models, adding a counter/stats sidecar
table, resolving a generic target back to its concrete object, or writing a migration that
converts a legacy GenericForeignKey to `DocumentId`.

---

### 6. Shared Services and GraphQL Interfaces
Two runtime registries replace cross-block imports. `SharedServiceProvider` exposes behaviour by
name (`shared_services.get("commentable_metadata")` — **always handle `None`**).
`strawberry_shared_interfaces` lets a block add fields to another block's type by name, with
unregistered names silently skipped. `apply_if_installed(...)` guards optional field lists.

Read `references/shared-services.md` when: exposing behaviour from a block, consuming another
block's data, opting a type into an interface, or making a block degrade gracefully when
an optional dependency is absent.

---

### 7. Query Optimization: Optimizer Hints
**Read this before any GraphQL performance work.** Every schema built with `build_schema` runs
strawberry-django's `DjangoOptimizerExtension`, which turns the selection set into `only` /
`select_related` / `prefetch_related` / `annotate`. `Node.id` adds the relay-id
(`mapped_public_id`) subquery automatically. What the walker can't see — columns a resolver or
permission check reads, annotations, virtual relations — you declare as hints on `django_type(...)`
or on the field. Getting this wrong is silent: the query returns correct data and issues one
round-trip per row.

Read `references/query-optimization.md` when: adding a type, adding a resolver that reads a model
field not exposed through GraphQL, seeing per-row `refresh_from_db` in the SQL log, or reviewing
any change to a type on a list path.

---

### 8. Field-Level Hints on Shared Interfaces
When a field belongs to a shared interface, put the hint on the *field*
(`strawberry_django.field(annotate=..., prefetch_related=...)`) rather than on every implementing
type. It applies only when that field is selected, and `model_from_info(info)` gives the
implementing model. This is also the only way to prefetch a *virtual relation* — one with no direct
FK, reached through `DocumentId`.

Read `references/optimizer-hooks.md` when: adding a field to a shared GraphQL interface, exposing
a count or flag that consumers shouldn't have to wire up, or optimizing a relation that routes
through `DocumentId`.

---

### 9. `annotate_queryset` and Metadata Sidecars
Counters live in a `*ableMetadata` sidecar keyed by `DocumentId`, maintained on the write path,
and read via a correlated `Subquery` annotation — always `Coalesce`d so a target with no metadata
row costs nothing. The service getters prefer the annotation and fall back to a query, which is
what makes annotating optional rather than mandatory. Annotations are also what make a field
filterable and orderable.

Read `references/annotate-queryset.md` when: adding a counter or aggregate to a block, exposing a
field that clients need to sort or filter by, converting a `@property` that hits the DB, or
maintaining a count on save/delete.

---

### 10. Connection Fields
Lists are `@connection(CountedConnection[XLazy] | None, filterset_class=XFilter)` from
`baseapp_core.strawberry.connections`: `offset` + FilterSet arguments, `totalCount` / `edgeCount`,
optimizer always on. Resolvers return unevaluated querysets. Relation connections come from
`django_type(relations=...)`, not hand-declared fields.

Read `references/connection-fields.md` when: adding any connection field, filtering or ordering a
list by an annotation, or returning an empty queryset from a resolver.

---

### 11. Query-Count Regression Tests
Optimization that isn't pinned by a test regresses. Two house styles: `graphql_client_with_queries`
for exact counts with a per-query explanation, and `CaptureQueriesContext` for upper bounds and
SQL-shape assertions. The strongest form asserts that **doubling the data doesn't change the
count**. Every assertion carries a ranked "likely cause" message.

Read `references/query-count-tests.md` when: finishing any optimization work, adding a type
on a list path, or reviewing a PR that changes a hint, an interface field, or a connection field.

---

## Definition of done for a new block

1. Package scaffolded, `plugin.py` + `apps.py` present.
2. Entry point, package-data, and `MANIFEST.in` stanza added.
3. `testproject/settings.py` updated *before* the `plugin_registry.load_from_installed_apps(...)`
   call; concrete swapped models and migrations added under `testproject/`.
4. Every list path guarded by a query-count test.
5. `docker compose run --rm web uv run --python 3.12 pytest baseapp/<name>/` green, coverage ≥ 75%.
   Bare `pytest` is a trap — see `references/query-count-tests.md`.
6. `black .`, `isort .`, `flake8`, and `uv run ast-grep scan` clean.
