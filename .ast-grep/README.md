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
docker compose run --rm --no-deps web uv run ast-grep scan
docker compose run --rm --no-deps web uv run ast-grep test
```

Run a single rule with `--filter <rule-id>`. If the `web` container is already
running, use `docker compose exec web ...` instead of `run` (see the
`run-development-commands` skill).

`ast-grep scan` exits non-zero only when a **severity: error** rule matches —
warnings and hints are informational.

All rules ignore `**/migrations/**` (auto-generated); the translation rules also
ignore `**/tests/**` (test fixtures are not user-facing). `django-admin-use-unfold`
and `django-translation-model-meta-verbose-name-required` are additionally scoped to
`apps/**` (project code): the `baseapp_*` packages here intentionally register stock
admins that consuming projects unregister and re-register with Unfold, and ship
abstract models whose `Meta` the project is expected to extend.

Both `sgconfig.yml` files map `*.j2` to the HTML language so the template rule also
covers Jinja email templates.

## Rules

The `See ...` paths in rule messages point at the `backend-conventions` /
`backend-patterns` skill reference files, which live in the consuming template
(`.claude/skills/`). In this repo the same conventions are summarized in
[`AGENTS.md`](../AGENTS.md) → Code Guidelines.

| Rule | Severity | Convention |
|---|---|---|
| `python-typing-required` | warning | Every function/method has a return type annotation (typing.md) |
| `django-translation-no-module-level-eager-gettext` | error | Module-level strings must not be evaluated with eager `gettext` (translations.md) |
| `django-translation-use-gettext-lazy` | error | `_` is always `gettext_lazy`; eager `gettext` only inside request-time bodies, imported by name (translations.md) |
| `django-translation-model-fields-lazy` | error | `verbose_name` / `help_text` / `label` wrapped in `_()` (translations.md) |
| `django-translation-meta-verbose-name-lazy` | error | `Meta.verbose_name` / `verbose_name_plural` and `AppConfig.verbose_name` wrapped in `_()` (translations.md) |
| `django-translation-model-meta-verbose-name-required` | error | `apps/**/models.py` only — every concrete model declares `Meta.verbose_name = _(...)`, even when extending a package abstract's `Meta` (translations.md) |
| `django-translation-choices-label-lazy` | error | `TextChoices` / `IntegerChoices` labels and inline `choices=[...]` labels wrapped in `_()` (translations.md) |
| `django-translation-validation-error-literal` | error | No bare string anywhere inside `ValidationError(...)` — positional, `detail=`, dict values, list items (translations.md, error-shape.md) |
| `django-translation-admin-labels-lazy` | error | `short_description` and `@admin.display` / `@admin.action` `description=` wrapped in `_()` (translations.md) |
| `django-translation-no-fstring-in-gettext` | error | No f-string / `%` / `.format()` / `+` inside `_()` and `gettext*()` — interpolate after translating (translations.md) |
| `django-template-untranslated-text` | error | Text and `alt` / `title` / `placeholder` attributes in `**/templates/**` go through `{% trans %}` / `{% blocktrans %}` / `{{ _() }}` (translations.md) |
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

### Suppressing a finding

A deliberate exception (a machine-readable error code in a `ValidationError`, a blank
Wagtail block label) is silenced with a comment on the **previous line** that names
the rule, plus a comment saying why:

```python
# Machine-readable error code consumed by clients, not user-facing copy.
# ast-grep-ignore: django-translation-validation-error-literal
raise serializers.ValidationError({"email": ["no_email_provided"]})
```

In templates use `<!-- ast-grep-ignore: django-template-untranslated-text -->`.

## Testing rules

Every rule has a test file in `rule-tests/` with `valid:` (must not match) and
`invalid:` (must match) snippets, plus accepted snapshots in `rule-tests/__snapshots__/`.

```bash
docker compose run --rm --no-deps web uv run ast-grep test       # verify
docker compose run --rm --no-deps web uv run ast-grep test -U    # accept new/changed snapshots
```

## Limitations

Some guidelines can't be enforced with AST patterns and stay in code-review territory:

- **Runtime strings.** Messages assembled from constants, dict lookups or variables
  (`ValidationError(MESSAGES[code])`, `raise ValidationError(message)`), strings in
  `fieldsets` titles, `list_display` tuples, `CONSTANCE_CONFIG` help texts, GraphQL
  `description=` and anything built outside a literal are invisible to ast-grep. The
  catalog freshness check only sees what `makemessages` extracts, so these need a
  reviewer.
- **`TextChoices` members without an explicit label** (`DRAFT = "draft"`) get an
  auto-generated English label Django never translates; the rule can only flag
  literal labels.
- **Templates.** The HTML parser sees a whole run of text between tags as one node, so
  prose that shares a node with a `{% ... %}` tag is skipped (false negative), and
  icon ligature names or `{% blocktrans %}` bodies split by inline tags can be reported
  (false positive). Suppress a false positive with an `ast-grep-ignore` comment; the
  `makemessages` freshness gate covers anything that does use the i18n tags.
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
