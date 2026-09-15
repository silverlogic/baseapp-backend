# Swappable Models

A concrete model in a block is a decision the consuming project can't undo. Making it swappable
lets a project substitute its own model — extra fields, different behaviour — while the block keeps
working against the abstract contract.

**Every concrete model a block defines should be swappable.** This repo uses `django-swappable-models`
(`swapper`). There is no `get_model_string` helper and no `SwappableModel` base class here.

## Block side — abstract + swappable setting

```python
import swapper
from baseapp_core.graphql import RelayModel
from baseapp_core.models import DocumentIdMixin, DocumentIdTargetMixin


class AbstractFoo(DocumentIdTargetMixin, TimeStampedModel, DocumentIdMixin, RelayModel):
    body = models.TextField(verbose_name=_("body"))

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_foo", "Foo")

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import FooObjectType

        return FooObjectType
```

Three requirements:

- `abstract = True` **and** `swappable = swapper.swappable_setting(<app_label>, <ModelName>)`. The
  app label is the underscore form, matching `AppConfig.label`.
- Inherit `RelayModel` from `baseapp_core.graphql` — supplies `relay_id`.
- Implement `get_graphql_object_type()` so consuming projects can swap the ObjectType too. Import
  inside the method.

## Everywhere else — load lazily

Never import the abstract class to use it. Load the swapped model at module level:

```python
Foo = swapper.load_model("baseapp_foo", "Foo")
app_label = Foo._meta.app_label
```

This is the top-of-module idiom in `admin.py`, `permissions.py`, `queries.py`, `mutations.py`,
`factories.py`, `signals.py`, and `object_types.py`.

Inside `models.py`, where the app registry isn't ready yet, use the core helper instead:

```python
from baseapp_core.swapper import init_swapped_models
```

`baseapp_core/swapper.py` provides two helpers:

| Helper | Use |
|---|---|
| `init_swapped_models([...])` | Inside `models.py`, before app configs are ready |
| `get_apps_model(apps, app_label, model)` | Inside **migrations**, to resolve a possibly-swapped model from the historical registry |

In migrations always use `get_apps_model` — `apps.get_model("baseapp_foo", "Foo")` fails outright
when the model has been swapped out.

## Referencing another block's model

By name, never by import:

```python
profile = models.ForeignKey(
    swapper.get_model_name("baseapp_profiles", "Profile"),
    on_delete=models.CASCADE,
    related_name="foos",
)
```

`related_name` is plural on `ForeignKey`/`ManyToManyField`, singular on `OneToOneField`.

## Optional cross-block fields

Mix them in at class-definition time so the model simply lacks the field when the other block is
absent:

```python
from django.apps import apps

inheritances = []
if apps.is_installed("baseapp_profiles"):

    class ProfileMixin(models.Model):
        profile = models.ForeignKey(
            swapper.get_model_name("baseapp_profiles", "Profile"),
            on_delete=models.CASCADE,
            related_name="foos",
        )

        class Meta:
            abstract = True

    inheritances.append(ProfileMixin)


class AbstractFoo(*inheritances, TimeStampedModel, RelayModel):
    ...
```

Pair this with `apply_if_installed(...)` in the GraphQL `Meta.fields` — see `shared-services.md`.
Cover it with a test in `tests/integration/` using `with_disabled_apps_context`.

## Consuming project side

The concrete model, its migrations, and the settings live in the project. In this repo that is
`testproject/`:

```python
# testproject/foo/models.py
from baseapp.foo.models import AbstractFoo


class Foo(AbstractFoo):
    class Meta(AbstractFoo.Meta):
        pass
```

```python
# testproject/settings.py
BASEAPP_FOO_FOO_MODEL = "foo.Foo"
```

The setting name is what `swapper.swappable_setting("baseapp_foo", "Foo")` generates:
`BASEAPP_<APP>_<MODEL>_MODEL`. Add `"testproject.foo"` to `INSTALLED_APPS` before
`load_from_installed_apps(...)`, and generate migrations in `testproject/foo/migrations/`.

**The block itself ships no migrations for swappable models.** See `package-scaffold.md`.

## When not to make a model swappable

Internal models with no reason to be extended — `baseapp_api_key`, `baseapp_message_templates`, and
`baseapp_url_shortening` ship concrete models plus their own migrations. If a consuming project
would never subclass it, a concrete model is simpler. Sidecar metadata tables *are* swappable,
because projects extend them.

## Anti-patterns

- Importing `AbstractFoo` to query it. Use `swapper.load_model`.
- `apps.get_model(...)` in a migration touching a swappable model. Use `get_apps_model`.
- A direct `ForeignKey` to another block's concrete model class. Use `swapper.get_model_name`.
- Shipping migrations for a swappable model.
- Omitting `get_graphql_object_type()` — the ObjectType then can't be swapped, so the model is only
  half-overridable.
- An unconditional FK to an optional block's model. Guard with `apps.is_installed`.
- App label mismatch between `swappable_setting`, `AppConfig.label`, and `swapper.load_model`.
