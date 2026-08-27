# Package Scaffold

A block is a Django app plus a plugin declaration. It lives in this repository, ships inside the
single `baseapp_backend` distribution, and is switched on by a consuming project adding it to
`INSTALLED_APPS`.

## Where new packages go

**Use `baseapp/<name>/`** — the namespaced layout, as in `baseapp/activity_log/` and
`baseapp/content_feed/`.

The ~24 root-level `baseapp_<name>/` directories are the older layout. They still hold the richest
examples (`baseapp_comments`, `baseapp_chats`), so read them for patterns — but put new code in the
namespace.

The mechanical differences:

| | `baseapp/foo/` | `baseapp_foo/` |
|---|---|---|
| Import path | `baseapp.foo` | `baseapp_foo` |
| Entry-point target | `baseapp.foo.plugin:FooPlugin` | `baseapp_foo.plugin:FooPlugin` |
| `AppConfig.name` | `"baseapp.foo"` | `"baseapp_foo"` |
| `AppConfig.label` | `"baseapp_foo"` — keep the underscore form, it is the DB table prefix and the swapper app label | `"baseapp_foo"` |

Keeping `label` in the underscore form matters: it becomes the migration app label, the table
prefix, and the first argument to `swapper.load_model(...)`.

## Layout

```
baseapp/foo/
├── __init__.py          # empty
├── apps.py              # PackageConfig — required
├── plugin.py            # FooPlugin — required
├── models.py            # abstract + swappable
├── admin.py
├── permissions.py       # a Django auth backend; compose with | and &
├── services.py          # SharedServiceProvider implementations
├── signals.py           # receivers; connect in ready() with dispatch_uid
├── README.md            # how to install / use / customise the model
├── graphql/
│   ├── __init__.py      # empty
│   ├── object_types.py  # Base<X>ObjectType + concrete <X>ObjectType
│   ├── interfaces.py    # lazy getters returning interface classes
│   ├── queries.py       # class FooQueries
│   ├── mutations.py     # class FooMutations
│   ├── subscriptions.py # optional
│   └── filters.py       # FilterSets, shared with DRF
├── rest_framework/      # only if the block has a REST surface
│   ├── __init__.py
│   ├── serializers.py
│   └── views.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── factories.py
    └── integration/     # "other block absent" scenarios
```

Only `__init__.py`, `apps.py`, and `plugin.py` are mandatory. Add the rest when the block needs
them — `baseapp_api_key` has no `graphql/object_types.py`; `baseapp_ratings` has no `signals.py`.

**Default to GraphQL.** Add `rest_framework/` only when the work is explicitly scoped to REST.

## Migrations

**A block with swappable models ships no `migrations/` directory.** The concrete model and its
migrations live in the consuming project — in this repo, `testproject/<name>/`. That is why
`baseapp_comments`, `baseapp_ratings`, `baseapp_blocks`, and most others have none.

Blocks with non-swappable concrete models (`baseapp_api_key`, `baseapp_message_templates`,
`baseapp_url_shortening`) do ship migrations. See `swappable-models.md` for the decision.

## `__init__.py` stays empty

No `default_app_config` — that is pre-Django-3.2 and appears nowhere in this repo. Discovery works
through `apps.py` with `default = True`.

Never import models, services, or GraphQL types at package import time. The plugin registry loads
before the app registry is ready, and an import-time model reference raises
`ImproperlyConfigured`.

## Factories need a real target

A model using `DocumentIdTargetMixin` has a **non-null** `target_document`. Its factory resolves it
from a `target` that must be a real, documentable object:

```python
class AbstractWidgetFactory(factory.django.DjangoModelFactory):
    target_document = factory.LazyAttribute(
        lambda o: DocumentId.get_or_create_for_object(o.target)
    )

    class Meta:
        exclude = ["target"]
        abstract = True
```

Callers must pass one — `WidgetFactory(target=some_profile)`. Passing `target=None` produces a
`NotNullViolation` on insert, not a friendly error. Any model with `DocumentIdMixin` works as a
target; `ProfileFactory()` is the usual choice in tests.

## Naming

| Thing | Convention |
|---|---|
| AppConfig class | `PackageConfig` (24 of 26 blocks) |
| Plugin class | `<Name>Plugin` — `RatingsPlugin`, `CommentsPlugin` |
| Service class | `<Name>Service` — `CommentableMetadataService` |
| Abstract model | `Abstract<Name>` — `AbstractRate` |
| Base ObjectType | `Base<Name>ObjectType`, concrete `<Name>ObjectType` |
| Metadata model | `Abstract<Thing>ableMetadata` — `AbstractCommentableMetadata` |
| Interface | `<Name>sInterface` — `CommentsInterface` |
| Settings | `BASEAPP_<NAME>_<SETTING>` |

The `Base<X>ObjectType` / `<X>ObjectType` split exists so consuming projects can build their own
concrete type from the base without inheriting the registration:

```python
class BaseCommentObjectType:
    class Meta:
        model = Comment
        ...

class CommentObjectType(BaseCommentObjectType, DjangoObjectType):
    class Meta(BaseCommentObjectType.Meta):
        pass
```

## README.md

Every block has one. `baseapp_ratings/README.md` is the template: how to install (what the plugin
contributes automatically), how to opt an ObjectType into the interface, how to read counts via the
shared service, and how to customise the swappable model.

## Anti-patterns

- Creating `baseapp_foo/` at the root for a new block. Use the namespace.
- Setting `label` to `"foo"` instead of `"baseapp_foo"` — changes table prefixes and breaks
  `swapper.load_model` lookups.
- Shipping migrations for a swappable model. They belong in the consuming project.
- Importing models or GraphQL types in `__init__.py` or at `plugin.py` module level.
- Adding a `rest_framework/` surface by default when nothing asked for REST.
