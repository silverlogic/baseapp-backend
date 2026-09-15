# Plugin Registration

A block contributes settings *declaratively* through `plugin.py`. Runtime behaviour is registered
separately in `apps.py` (see `app-config-wiring.md`). Keeping the two apart is what lets settings be
aggregated before Django's app registry is ready.

Registration touches four files. Miss one and the block loads but contributes nothing — no error.

## 1. `plugin.py`

```python
from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class FooPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_foo"          # underscore form — the identity/label

    @property
    def package_name(self) -> str:
        return "baseapp.foo"          # IMPORT PATH — matched against INSTALLED_APPS

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_foo": ["baseapp.foo.permissions.FooPermissionsBackend"],
            },
            django_extra_settings={
                "BASEAPP_FOO_CAN_ANONYMOUS_VIEW": True,
                "BASEAPP_FOO_MAX_PER_THREAD": None,
            },
            graphql_queries=["baseapp.foo.graphql.queries.FooQueries"],
            graphql_mutations=["baseapp.foo.graphql.mutations.FooMutations"],
            required_packages=[],
            optional_packages=[
                {"baseapp_profiles": "If enabled, foos can be tied to a Profile"},
            ],
        )
```

**`name` and `package_name` are not the same thing in the namespaced layout.** `package_name` is
the dotted import path and is what `PluginRegistry` compares against `INSTALLED_APPS` to decide
whether to load the plugin at all — get it wrong and the block is silently skipped. `name` is the
underscore identity, matching `AppConfig.label`. In the older root layout both are
`"baseapp_foo"`, which is why the difference is easy to miss.

`INSTALLED_APPS=[]` is normal: the block itself is already in `INSTALLED_APPS` (that is what
activated the plugin). Use this field only to pull in *third-party* apps the block needs.

### `PackageSettings` fields

`PackageSettings` is a pydantic model with `populate_by_name=True`, so Django-style aliases map to
snake_case fields.

| Category | Field (alias) | Shape |
|---|---|---|
| List | `installed_apps` (`INSTALLED_APPS`) | `List[str]`, aggregated |
| Slotted | `middleware` (`MIDDLEWARE`) | `Dict[slot, List[str]]` |
| Slotted | `authentication_backends` (`AUTHENTICATION_BACKENDS`) | `Dict[slot, List[str]]` |
| Slotted | `graphene_middleware` (`GRAPHENE__MIDDLEWARE`) | `Dict[slot, List[str]]` |
| Dict | `django_extra_settings` | merged into Django settings |
| Dict | `celery_beat_schedules`, `celery_task_routes`, `constance_config` | merged; last plugin wins |
| List | `urlpatterns`, `v1_urlpatterns` | callbacks, see below |
| List | `graphql_queries`, `graphql_mutations`, `graphql_subscriptions` | **dotted strings** |
| Deps | `required_packages`, `optional_packages` | `str` or `{name: why}` |

**Slotted fields are dicts, not lists.** The key is a slot name (conventionally the block's own
label) so `settings.py` can control ordering with `plugin_registry.get("MIDDLEWARE", "baseapp_foo")`.
Passing a bare list will not validate.

`required_packages` is enforced: `validate()` raises `ImproperlyConfigured` at settings-load time
if a required app isn't in `INSTALLED_APPS`. `optional_packages` is documentation — guard optional
behaviour at runtime with `apps.is_installed(...)` or a `shared_services.get(...)` `None` check.

**GraphQL roots are dotted strings, resolved later with `import_string`.** Never import the actual
class in `plugin.py`; it runs before the app registry is ready.

### URLs

URL patterns are contributed as a **callback**, so nothing imports views at module load:

```python
    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            required_packages=["baseapp_core"],
            v1_urlpatterns=self.v1_urlpatterns,
        )

    @staticmethod
    def v1_urlpatterns(include, path, re_path) -> "list[URLResolver]":
        from baseapp.foo.rest_framework.routers import foo_router
        return [re_path(r"", include(foo_router.urls))]
```

`baseapp_notifications/plugin.py` shows conditional URLs guarded by `apps.is_installed(...)`.

## 2. `pyproject.toml` — the entry point

This is what makes the plugin discoverable. `stevedore` scans the `baseapp.plugins` namespace.

```toml
[project.entry-points."baseapp.plugins"]
baseapp_foo = "baseapp.foo.plugin:FooPlugin"
```

> `baseapp_core/plugins/README.md` says these go in a root `setup.cfg` under
> `[options.entry_points]`. **That file does not exist.** The README is stale; use
> `pyproject.toml`.

Also add package data if the block ships templates, static files, or locales. The key is a
**package name**, so for the namespaced layout it is the quoted dotted path — not the underscore
form:

```toml
[tool.setuptools.package-data]
"baseapp.foo" = ["*.j2", "*.html", "*.png"]
```

Getting this wrong fails silently: `baseapp_foo` is a valid identifier, so setuptools accepts the
key, matches it against no package, and simply ships none of your data files. Note also that the
existing `baseapp = [...]` entry covers only files directly in `baseapp/` — `package-data` keys are
exact package names, not recursive, so it does **not** cover `baseapp/foo/`. (Neither of the two
existing namespaced blocks declares one; they ship no data files, so it has never come up.)

Skip this entirely if the block has no templates, static files, or locales — most don't.

And an extra **only if the block needs new third-party dependencies**:

```toml
[project.optional-dependencies]
foo = ["some-lib>=1.2"]
```

Most blocks need none — `baseapp_comments`, `baseapp_ratings`, `baseapp_blocks`, and
`baseapp_follows` all have no extra. If you do add one, add it to the self-install list in
`[dependency-groups]` too, or the test project won't have it. Use
`uv add --optional foo some-lib`.

Editing entry points requires reinstalling the distribution before they take effect.

## 3. `MANIFEST.in`

```text
include baseapp/foo/README.md
recursive-include baseapp/foo/templates *
recursive-include baseapp/foo/static *
recursive-include baseapp/foo/locale *
```

## 4. `testproject/settings.py`

```python
INSTALLED_APPS += ["baseapp.foo", "testproject.foo"]

plugin_registry.load_from_installed_apps(installed_apps=INSTALLED_APPS)
INSTALLED_APPS += plugin_registry.get("INSTALLED_APPS")
```

**Add the app before `load_from_installed_apps(...)`.** Anything appended after that call is
invisible to the registry — the single most common reason a new plugin "doesn't load".

If the block ships an auth backend, slot it in:

```python
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_foo"),
]
```

Swappable models also need their settings here — see `swappable-models.md`.

Note how extra settings are applied, near the bottom of the file:

```python
plugin_settings = plugin_registry.get_all_django_extra_settings()
for key, value in plugin_settings.items():
    if key not in globals():
        globals()[key] = value
# Anything after this line will override the plugin settings.
```

`if key not in globals()` means a value already defined above wins. Your
`django_extra_settings` are **defaults**, not overrides.

## Verifying registration

```python
from baseapp_core.plugins import plugin_registry
plugin_registry.get("INSTALLED_APPS")
plugin_registry.get_all_graphql_queries()
plugin_registry.get_all_django_extra_settings()
```

If your block is absent: check `package_name` matches the `INSTALLED_APPS` string exactly, that the
app was added before `load_from_installed_apps`, and that the distribution was reinstalled after
the entry point changed.

## Anti-patterns

- `package_name` set to the underscore form in the namespaced layout. Plugin never loads.
- Importing views, models, or GraphQL classes at `plugin.py` module level.
- Passing a list to a slotted field.
- Adding the app to `INSTALLED_APPS` after `load_from_installed_apps(...)`.
- Following the README's `setup.cfg` / `requirements.txt` instructions.
- Expecting `django_extra_settings` to override a value already set in `settings.py`.
- Listing a genuinely required block in `optional_packages` — you lose the startup check.
