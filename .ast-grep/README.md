# ast-grep Rules

[ast-grep](https://ast-grep.github.io/) rules that statically enforce the BaseApp
backend code guidelines. The rules live here in **baseapp-backend** and are shared
with consuming projects the same way the agent skills are: the template symlinks
`.ast-grep` → `baseapp-backend/.ast-grep` and keeps its own `sgconfig.yml` at the
repo root.

They run on **both CI surfaces**:

- **GitHub Actions** (this repo) — the `ast-grep` step in
  `.github/workflows/github-actions.yml` runs `ast-grep test` + `ast-grep scan`
  against the packages.
- **Jenkins** (consuming template) — the `AstGrep` lint stage scans the project,
  excluding this submodule (linted here) via `--globs '!baseapp-backend'`.

## Installation

Nothing to install on the host. `ast-grep-cli` is a uv dev dependency in both repos,
so it is available inside the `web` Docker service — the same way flake8/black/isort
run.

## Usage

From a **consuming project** root (the submodule is excluded — it's linted in this
repo's own CI):

```bash
docker compose run --rm --no-deps web uv run ast-grep scan --globs '!baseapp-backend'
docker compose run --rm --no-deps web uv run ast-grep test
```

From **this repo's** root:

```bash
docker compose exec -T web uv run ast-grep scan
docker compose exec -T web uv run ast-grep test
```

Run a single rule with `--filter <rule-id>`. If the `web` container is already
running in the template, use `docker compose exec web ...` (see the
`run-development-commands` skill).

`ast-grep scan` exits non-zero only when a **severity: error** rule matches —
warnings and hints are informational.

All rules ignore `**/migrations/**` (auto-generated). `django-admin-use-unfold` is
additionally scoped to `apps/**` (project code): the `baseapp_*` packages here
intentionally register stock admins that consuming projects unregister and
re-register with Unfold.

## Rules

The `See ...` paths in rule messages point at the `backend-conventions` /
`backend-patterns` skill reference files, which live in the consuming template
(`.claude/skills/`). In this repo the same conventions are summarized in
[`AGENTS.md`](../AGENTS.md) → Code Guidelines.

| Rule | Severity | Convention |
|---|---|---|
| `python-typing-required` | warning | Every function/method has a return type annotation (typing.md) |
| `django-translation-no-module-level-eager-gettext` | error | Module-level strings must not be evaluated with eager `gettext` (translations.md) |
| `django-translation-use-gettext-lazy` | hint | Prefer `gettext_lazy as _`; eager `gettext` only inside request-time bodies (translations.md) |
| `django-translation-model-fields-lazy` | warning | `verbose_name` / `help_text` / `label` wrapped in `_()` (translations.md) |
| `django-related-name-required` | warning | Explicit `related_name` on FK / M2M / O2O (models.md) |
| `django-use-timezone-now` | warning | `timezone.now()` instead of naive `datetime.now()` / `utcnow()` (datetime.md) |
| `django-admin-use-unfold` | error | `apps/**` only — subclass `unfold.admin.ModelAdmin` / inlines, never stock `django.contrib.admin` (admin.md) |
| `django-property-instead-of-annotation` | warning | QuerySet `add_*` annotations over per-instance `@property` queries (queryset-annotations.md) |
| `drf-validation-error-format` | warning | `ValidationError({field: [msg]})`, messages always in a list (error-shape.md) |
| `drf-validation-in-viewset` | warning | Validate via Serializer, not `request.data` reads in view methods (drf-file-layout.md) |
| `drf-filters-in-viewset` | warning | Filter via FilterSet, not `request.GET` / `request.query_params` (drf-file-layout.md) |
| `exception-handling-without-logging` | warning | Broad `except Exception` must `logger.exception(...)` or re-raise (error-shape.md) |
| `graphql-use-django-object-type` | error | Import `DjangoObjectType` from `baseapp_core.graphql`, not `graphene_django` (graphql-file-layout.md) |
| `graphql-use-relay-mutation` | warning | Mutations inherit `RelayMutation`, not `graphene.Mutation` (graphql-file-layout.md) |
| `graphql-use-relay-model` | hint | Models exposed via GraphQL inherit `RelayModel` (only `models.py` files; ast-grep can't tell which models are exposed, hence hint) (graphql-file-layout.md) |

## Testing rules

Every rule has a test file in `rule-tests/` with `valid:` (must not match) and
`invalid:` (must match) snippets, plus accepted snapshots in `rule-tests/__snapshots__/`.

```bash
docker compose exec -T web uv run ast-grep test       # verify
docker compose exec -T web uv run ast-grep test -U    # accept new/changed snapshots
```

## Limitations

Some guidelines can't be enforced with AST patterns and stay in code-review territory:

- `related_name` **plurality** (plural FK/M2M vs singular O2O) — grammar, not syntax.
- `get_node` permission checks on ObjectTypes — presence is checkable, correctness isn't.
- ISO 8601 serialization, UTC storage at runtime, docstring quality, queryset
  optimization (`select_related` / N+1), permission granularity, file-placement rules
  (`permissions.py` / `filtersets.py` splits).

## Contributing new rules

1. Add `rules/<category>-<feature>.yml` (keep the `**/migrations/**` ignore; do NOT
   add path ignores that could match the repo's own checkout directory name).
2. Add `rule-tests/<rule-id>-test.yml` with valid/invalid cases.
3. Run `ast-grep test -U` in Docker and commit the snapshot.
4. Make sure `ast-grep scan` stays error-free in BOTH repos — new `severity: error`
   rules must either pass on the `baseapp_*` packages or be scoped with `files:`
   like `django-admin-use-unfold`.
5. Point `message` at the relevant skill reference file and add a row to the table above.
