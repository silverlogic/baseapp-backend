# BaseApp Pages

Reusable app for pages, URL paths, and SEO metadata. It provides the `URLPath` and `Metadata` tables that any model can attach to (via `DocumentId` / generic relations), a swappable `Page` model, and the `PageInterface` GraphQL interface.

`baseapp_pages` follows the [plugin architecture](../baseapp_core/plugins/README.md): it registers itself as a plugin for settings aggregation and wires its permissions backend, GraphQL roots, the `pages.url_path` shared service, and the `PageInterface` shared interface through the registry — no direct cross-package imports.

## Whats missing
- [ ] Allow for custom settings.LANGUAGES per project
- [ ] Make create migration work with TranslatedField

Currently if you have a different set of languages in your project it will create a new migration changing the fields. So if you have a migration check test it will fail because the `settings.LANGUAGES` are different.

## How to install

Install the package with `pip install baseapp-backend[pages]`, plus its 3rd-party dependency `pip install django-quill-editor==0.1.42`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

The package registers itself as a plugin (see `baseapp_pages.plugin:PagesPlugin`), so most wiring goes through `plugin_registry`.

1. Add `baseapp_pages` and `django_quill` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_pages",
    "django_quill",
    # ...
]
```

2. Add `django.middleware.locale.LocaleMiddleware` to `MIDDLEWARE` so the active language drives URL-path / metadata resolution ([Django docs](https://docs.djangoproject.com/en/5.0/topics/i18n/translation/#how-django-discovers-language-preference)).

3. Wire the auth backend slot — `PagesPermissionsBackend` is contributed via the registry:

```python
AUTHENTICATION_BACKENDS = [
    # ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_pages"),
    # ...
]
```

4. Make sure your project's `graphql.py` composes the schema via `plugin_registry.get_all_graphql_*()` so `PagesQueries` (`urlPath`, `page`, `allPages`) and `PagesMutations` (`pageCreate`, `pageEdit`, `pageDelete`) are picked up automatically.

5. Define the concrete `Page` model (see [models](#models)) and point the swapper setting at it:

```python
BASEAPP_PAGES_PAGE_MODEL = "pages.Page"
```

Run `./manage.py migrate` after defining it.

## Models

`URLPath` and `Metadata` are **concrete** models shipped (with migrations) by the package. `Page` is abstract + swappable — your project provides the concrete model (see [How to develop](#how-to-develop)).

| Model | Kind | Purpose |
|---|---|---|
| `URLPath` | concrete | A path (e.g. `/about`) for a target object, per `language`, with an `is_active` flag. `path` is unique; a partial unique constraint enforces one active `(path, language)`. |
| `Metadata` | concrete | Per-language SEO metadata (`meta_title`, `meta_description`, `meta_robots`, `meta_og_type`, `meta_og_image`) for a target object. |
| `AbstractPage` → `Page` | abstract + swappable | A content page: `user`, translated `title` / `body` (Quill), `status` (draft/published). |

Both `URLPath` and `Metadata` reference their target through a `GenericForeignKey` and inherit `DocumentIdMixin`, so any model can own paths/metadata without a direct FK.

### PageMixin

`PageMixin` adds no database columns — it adds reverse generic relations (`url_paths`, `metadatas`) plus a `url_path` property that returns the best active path for the current language. Inherit it on any model that should own URL paths / metadata:

```python
from baseapp_pages.models import PageMixin

class MyModel(PageMixin, models.Model):
    ...
```

(`baseapp_profiles.Profile` already inherits `PageMixin`, which is how profiles own URL handles.)

## GraphQL

### Queries (`PagesQueries`)

| Field | Description |
|---|---|
| `urlPath(path)` | Resolve a path to its `URLPath` for the active language, falling back to the active path for the same target when the matched row is inactive. |
| `page(id)` | RelayNode fetch of a single `Page`. |
| `allPages` | Filterable connection of pages (`PageFilter`, by `status`). |

`urlPath` example:

```graphql
{
    urlPath(path: "/about") {
        path
        language
        target {
            metadata {
                metaTitle
            }
            ... on Page {
                title
            }
        }
    }
}
```

### Mutations (`PagesMutations`)

| Field | Purpose |
|---|---|
| `pageCreate` | Create a page. |
| `pageEdit` | Edit a page. |
| `pageDelete` | Delete a page (`DeleteNode`). |

### Shared GraphQL interface — `PageInterface`

Pages **publishes** `PageInterface` via the registry — consume it by name (no direct import). Fields:

- `urlPath` — the active `URLPath` for the current language.
- `urlPaths` — all `URLPath` rows for the object (including inactive / other languages).
- `metadata` — the `Metadata` for the object.

```python
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class MyModelObjectType(DjangoObjectType):
    class Meta:
        model = MyModel
        interfaces = graphql_shared_interfaces.get(RelayNode, "PageInterface")
```

Object types implementing `PageInterface` should provide a `resolve_metadata`. To synthesize metadata from the instance:

```python
from django.apps import apps


class MyModelObjectType(DjangoObjectType):
    # ... Meta as above ...

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        if apps.is_installed("baseapp_pages"):
            from baseapp_pages.graphql.object_types import MetadataObjectType

            return MetadataObjectType(
                meta_title=instance.title,
                meta_description=instance.body[:160],
                meta_og_image=instance.image.url,
                meta_robots="noindex,nofollow",
            )
        return None
```

To support `Metadata` being set/overridden in the admin, fall back to a stored row first:

```python
    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        from django.contrib.contenttypes.models import ContentType
        from django.utils.translation import get_language
        from baseapp_pages.graphql.object_types import MetadataObjectType

        target_content_type = ContentType.objects.get_for_model(instance)
        metadata = MetadataObjectType._meta.model.objects.filter(
            target_content_type=target_content_type,
            target_object_id=instance.id,
            language=get_language(),
        ).first()
        return metadata or MetadataObjectType(meta_title=instance.title)
```

`PageObjectType` itself composes `PageInterface`, `PermissionsInterface`, and (by name) `CommentsInterface`.

## Shared service — `pages.url_path`

Pages registers a `pages.url_path` shared service (`URLPathService`) in `apps.ready()`. It owns URL-path **persistence and uniqueness** — callers build the handle, the service resolves collisions. This is what `baseapp_profiles` uses to mint profile handles (see the [profiles README](../baseapp_profiles/README.md#url-paths)).

```python
from baseapp_core.plugins import shared_services

if service := shared_services.get("pages.url_path"):
    # Suggest a free, collision-resolved path candidate (not concurrency-safe on its own).
    candidate = service.generate_url_path_str("/about")        # -> "/about" or "/about1" if taken

    # Create the URLPath, retrying with deterministic numeric suffixes on insert conflicts.
    url_path = service.create_url_path(
        instance, candidate, language=None, is_active=True, generate_path_str=False
    )
```

- `generate_url_path_str(path)` — returns a free candidate by checking existing rows and bumping a numeric suffix; not concurrency-safe by itself.
- `create_url_path(instance, path, *, language=None, is_active=True, generate_path_str=True)` — persists `instance.url_paths.create(...)`. With `generate_path_str=True` it does the final, concurrency-safe conflict resolution via DB-unique-constraint insert retries; with `generate_path_str=False` it persists the path as-is and raises on conflict (use when `path` already came from `generate_url_path_str`).

## Permissions

`PagesPermissionsBackend` gates `view_page` (and related page permissions). Subclass it to customize, then replace the plugin entry in `AUTHENTICATION_BACKENDS` with your subclass:

```python
AUTHENTICATION_BACKENDS = [
    # ...
    # *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_pages"),
    "myapp.permissions.MyPagesPermissionsBackend",
    # ...
]
```

## How to develop

General development instructions can be found in the [main README](../README.md#how-to-develop).

### Prerequisites when activating `baseapp_pages`

`Page` is abstract + swappable, so create a local app (we suggest `apps/pages/`) implementing the concrete model:

```python
from baseapp_pages.models import AbstractPage


class Page(AbstractPage):
    class Meta(AbstractPage.Meta):
        pass
```

Then point swapper at it:

```python
BASEAPP_PAGES_PAGE_MODEL = "pages.Page"
```

`URLPath` and `Metadata` are provided concretely by the package, so no extra models are needed for them.
