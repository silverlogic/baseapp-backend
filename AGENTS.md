# BaseApp Backend — Agent Guide

## What This Repo Is

BaseApp Backend is a monorepo of reusable Django packages (auth, profiles, comments, reactions, follows, blocks, chats, notifications, payments, etc.). It is consumed as a git submodule by project templates.

**Core stack:** Django + DRF + Graphene Django (GraphQL) + Celery + PostgreSQL + Redis.

**Dual API surface:** Some features expose both a REST API (DRF) and a GraphQL API (Graphene Django with Relay). When adding features, default to GraphQL API, unless scoped otherwise.

**Making ObjectTypes overridable:** Models should expose `get_graphql_object_type()` so consuming projects can swap the ObjectType. Use `get_object_type_for_model()` throughout package code instead of importing the ObjectType directly.

**Model swapping:** When adding a concrete model to a package, use `django-swappable-models` so consuming projects can substitute their own model.

## Code Guidelines

### Python
- Type-annotate all function parameters and return values.
- Add docstrings to non-trivial functions.
- All datetimes must be UTC; serialize as ISO 8601.

### Django Models
- Prefer queryset annotations over `@property` — annotations are filterable and avoid extra DB hits.
- If an annotation is reused, add it to a custom `QuerySet` method on a custom `Manager`.
- `related_name` on `ForeignKey`/`ManyToManyField` → plural; on `OneToOneField` → singular.
- Use `gettext_lazy as _` for all user-facing strings (`verbose_name`, `help_text`, form labels, error messages). Never use eager `gettext` at module level.

### DRF
- Put permissions in `permissions.py`; compose with `|` and `&` rather than bundling logic into one class.
- Validate request data with a `Serializer`, not inline in the view.
- Use `FilterSet` classes rather than manually parsing `request.GET`.
- `ValidationError` messages must be wrapped in an array; use `non_field_errors` for non-field errors.
- Catch exceptions, log them, and return a generic error — never expose exception details to the client.
- Serialize choice fields by returning the key, not the display value.

### GraphQL
- Models inherit `RelayModel` from `baseapp_core.graphql`.
- ObjectTypes use `baseapp_core.graphql.DjangoObjectType` and implement `get_graphql_object_type()`.
- Mutations inherit `RelayMutation` (provides `clientMutationId`, `errors`, `_debug`).
- Always permission-check in `get_node` to prevent unauthorized access via `node(id: ...)`.
- Put permissions in `permissions.py` and make use of Django's permissions system, which can also be shared with DRF as well.
- Consider `graphene-django-query-optimizer` for complex cases or optimize with `select_related`/`prefetch_related` in `get_queryset`; 
- Use `DjangoFilterConnectionField` + `FilterSet` for filterable list queries. `filters.py` can be shared with  DRF as well.
- Document queries and mutations with docstrings and `description=` / `deprecated_reason=` fields.

**Formatting:** Black with `line-length=100`, isort with Black profile.

## Test Structure

Each package follows this layout:

```text
baseapp_<package>/tests/
├── integration/   # DB-dependent tests
├── unit/          # pure logic, no I/O
├── factories.py   # factory-boy factories
├── fixtures.py    # pytest fixtures
└── helpers.py     # shared test utilities
```

## Commands

Run these from **this submodule's** root (`baseapp-backend/`) using its own `docker-compose.yml`.
Do **not** use a consuming template's container: it runs the template's `settings.*` (not
`testproject.settings`) and its pytest config ignores `baseapp-backend`, so package tests won't run
there. Paths below are relative to the submodule root.

```bash
# All tests
docker compose run --rm web pytest

# Specific package
docker compose run --rm web pytest baseapp_profiles/tests/

# Reuse the test DB across runs (skips the slow migrate/setup step)
docker compose run --rm web pytest baseapp_profiles/tests/ --reuse-db

# With coverage
docker compose run --rm web pytest --cov --cov-report=term-missing

# Code quality
docker compose run --rm web black .
docker compose run --rm web isort .
docker compose run --rm web flake8
docker compose run --rm web uv run ast-grep scan    # code-guideline rules (.ast-grep/rules/), if the project has them
docker compose run --rm web pre-commit run --all-files
```

## Test Coverage Policy

- Minimum coverage: **75%**
- A task is only complete when tests are written, all pass, and coverage is ≥ 75%.

## For AI Agents

- Use the `ensure-test-coverage` skill whenever implementing or modifying backend code.
- Use the `run-development-commands` skill to translate intent into the correct Docker Compose commands.
- Do not mark a task done until tests pass and coverage meets the threshold.
