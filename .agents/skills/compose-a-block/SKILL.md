---
name: compose-a-block
version: 1.0.0
description: ALWAYS use this skill when creating, extending, or reviewing a reusable package ("block") inside the baseapp-backend monorepo, and whenever GraphQL query performance is in play anywhere in this repo. Trigger on requests like "add a new baseapp package for X", "scaffold baseapp_foo", "wire up a plugin", "register a shared service", "expose this via a GraphQL shared interface", "make this model swappable", "why is this query doing N+1", "this list endpoint is slow", "add a counter field without a query per row", "add a pre_optimization_hook", "annotate this queryset", "the optimizer isn't picking up my prefetch", or "add a query-count regression test". Covers package scaffolding, plugin.py + PackageSettings, entry-point registration, AppConfig contributor mixins, swappable models, the DocumentId decoupling layer, shared services / GraphQL shared interfaces, and the full query-optimization stack (pre_optimization_hook, field-level optimizer_hook, annotate_queryset, connection-field choice, escape hatches, query-count tests). Skip ONLY for work in a consuming template's apps/ directory, dependency bumps, and doc-only edits.
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

**Use this skill for** work inside this repository — `baseapp/<name>/` or `baseapp_<name>/`.

**Do not use it for** work in a consuming template's `apps/` directory. That is project code; it
consumes blocks rather than defining them, and the template ships its own `backend-conventions`
and `backend-patterns` skills for it.

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

## Before you start: two known-stale sources

`baseapp_core/plugins/README.md` is the longest description of the architecture and is partly
wrong. It says entry points live in a root `setup.cfg` (that file does not exist — they are in
`pyproject.toml`), tells you to add `-e ./baseapp_yourpackage` to a `requirements.txt` (this is one
distribution managed by `uv`; there is nothing to install per package), and shows
`register_graphql_shared_interfaces(self)` without the `registry` argument every real `apps.py`
takes. Read it for the *why*; take the *how* from this skill.

The repo also depends on **two** optimizer libraries with confusingly similar names:
`graphene-django-query-optimizer` (imported as `query_optimizer`) and `graphene-django-optimizer`
(imported as `gql_optimizer`). Only the first is live. See section 7 before touching either.

---

## Sections

### 1. Package Scaffold
New packages go in `baseapp/<name>/` (the namespaced layout used by the two newest blocks), not
`baseapp_<name>/` at the root. `__init__.py` is empty; `apps.py` and `plugin.py` are mandatory;
`models.py`, `services.py`, `graphql/`, `permissions.py`, `signals.py`, `admin.py`, and `README.md`
are added as needed. Blocks with swappable models ship **no migrations** — the concrete models and
their migrations live in `testproject/`.

Read `references/package-scaffold.md` when: starting a new block, deciding which modules a block
needs, or checking whether an existing block is missing a conventional file.

---

### 2. Plugin Registration
`plugin.py` defines a `BaseAppPlugin` subclass returning a pydantic `PackageSettings`: installed
apps, slotted middleware/auth backends, extra Django settings, URL callbacks, GraphQL root
classes, and declared package dependencies. Registration then touches `pyproject.toml` (entry
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
Declare the model `abstract = True` with `swappable = swapper.swappable_setting(...)`, expose
`get_graphql_object_type()`, and load it everywhere else with `swapper.load_model(...)` at module
level. Optional cross-block fields are mixed in at class-definition time behind
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
`graphql_shared_interfaces` lets a block add fields to another block's ObjectType by name, with
unregistered names silently skipped. `apply_if_installed(...)` guards optional field lists.

Read `references/shared-services.md` when: exposing behaviour from a block, consuming another
block's data, opting an ObjectType into an interface, or making a block degrade gracefully when
an optional dependency is absent.

---

### 7. Query Optimization: `pre_optimization_hook`
**Read this before any GraphQL performance work.** `baseapp_core.graphql.DjangoObjectType`
subclasses `query_optimizer.DjangoObjectType` (from `graphene-django-query-optimizer`) — *not*
`graphene_django_optimizer`, which is present but dead. The base hook recursively injects the
relay-id subquery; blocks override it to force deferred columns into `only_fields`, add
`select_related`, or apply annotations. Getting this wrong is silent: the query returns correct
data and issues one round-trip per row.

Read `references/query-optimization.md` when: adding an ObjectType, adding a resolver that reads a
model field not exposed through GraphQL, seeing per-row `refresh_from_db` in the SQL log, or
reviewing any change to an ObjectType on a list path.

---

### 8. Field-Level `optimizer_hook`
When a field belongs to a shared interface, put the optimization on the *field* rather than in
every consuming ObjectType's `pre_optimization_hook`. The compiler calls `field.optimizer_hook`
only when that field is selected, so the cost is never paid by queries that don't ask for it. This
is also the only way to prefetch a *virtual relation* — one with no direct FK, reached through
`DocumentId`.

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
`query_optimizer.DjangoConnectionField` runs the optimizer.
`graphene_django.filter.DjangoFilterConnectionField` does **not** — under it,
`pre_optimization_hook` and every `optimizer_hook` become dead code. About half this repo still
uses the latter, so choosing the wrong one silently discards all the work from sections 7–9. Also
covers `CountedConnection`, `skip_ast_walker`, and nested same-type connections.

Read `references/connection-fields.md` when: adding any connection field, optimizing a list that
ignores your hook, returning an empty queryset from a resolver, or building a self-referencing
connection.

---

### 11. Query-Count Regression Tests
Optimization that isn't pinned by a test regresses. Two house styles: `graphql_client_with_queries`
for exact counts with a per-query explanation, and `CaptureQueriesContext` for upper bounds and
SQL-shape assertions. The strongest form asserts that **doubling the data doesn't change the
count**. Every assertion carries a ranked "likely cause" message.

Read `references/query-count-tests.md` when: finishing any optimization work, adding an ObjectType
on a list path, or reviewing a PR that changes a hook, an interface field, or a connection field.

---

## Definition of done for a new block

1. Package scaffolded, `plugin.py` + `apps.py` present.
2. Entry point, package-data, and `MANIFEST.in` stanza added.
3. `testproject/settings.py` updated *before* the `plugin_registry.load_from_installed_apps(...)`
   call; concrete swapped models and migrations added under `testproject/`.
4. Every list path guarded by a query-count test.
5. `docker compose run --rm web pytest baseapp/<name>/` green, coverage ≥ 75%.
6. `black .`, `isort .`, `flake8`, and `uv run ast-grep scan` clean.
