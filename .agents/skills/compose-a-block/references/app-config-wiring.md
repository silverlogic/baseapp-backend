# AppConfig Wiring

`plugin.py` declares *settings*. `apps.py` registers *runtime behaviour* — shared services, GraphQL
interfaces, serializers, signal receivers. The split exists because settings must be aggregated
before Django's app registry is ready, while runtime registration must happen after.

## The shape

```python
from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp.foo"            # dotted import path
    label = "baseapp_foo"           # underscore form — DB prefix + swapper app label
    verbose_name = _("BaseApp Foo")
    default_auto_field = "django.db.models.BigAutoField"

    def register_shared_services(self, registry) -> None:
        from .services import FooableMetadataService

        registry.register(FooableMetadataService())

    def register_graphql_shared_interfaces(self, registry) -> None:
        from .graphql.interfaces import get_foos_interface

        registry.register("FoosInterface", get_foos_interface)
```

`BaseAppConfig.ready()` dispatches by `isinstance` against each mixin, so you implement only the
hooks you declare. Class name is `PackageConfig` by convention.

`verbose_name` is user-facing — it labels the app in the Django admin — so wrap it in
`gettext_lazy`, never eager `gettext`: `apps.py` is imported during app loading, well before the
active locale is known, and an eager call would freeze the string at import time. Note that isort
treats `django.*` as third party and `baseapp_*` as first party, so the translation import sorts
into the block *above* any `baseapp_core` import.

## Contributor mixins

| Mixin | Method | Registers |
|---|---|---|
| `ServicesContributor` | `register_shared_services(self, registry)` | `SharedServiceProvider` instances |
| `GraphQLContributor` | `register_graphql_shared_interfaces(self, registry)` | interface getters, by name |
| `SerializersContributor` | `register_shared_serializers(self, registry)` | DRF serializers, by key |

> `baseapp_core/plugins/README.md` shows `register_graphql_shared_interfaces(self)` without the
> `registry` argument. That is stale — every real `apps.py` takes `registry`.

Note the asymmetry: services register themselves by their own `service_name` property
(`registry.register(FooableMetadataService())`), while interfaces and serializers are registered
under an explicit key.

Multiple registrations per hook are fine — `baseapp/activity_log/apps.py` registers three
interfaces in one call.

`SerializersContributor` example, `baseapp_profiles/apps.py`:

```python
    def register_shared_serializers(self, registry: SharedSerializerRegistry) -> None:
        from .rest_framework.serializers import JWTProfileSerializer

        registry.register("profiles.jwt_profile", JWTProfileSerializer)
```

## Imports go inside the methods

Every import in `apps.py` is function-local. Importing models or GraphQL types at module level runs
before the app registry is ready and raises `ImproperlyConfigured`. The registries enforce this —
their accessors are wrapped in `@require_django_ready` (`baseapp_core/plugins/readiness.py`), which
raises with a backtrace if called at import time.

## Signals

Override `ready()` only to import the signals module, and **call `super().ready()` first** or the
contributor hooks never fire:

```python
    def ready(self) -> None:
        super().ready()
        import baseapp.foo.signals  # noqa: F401
```

Receivers live in `signals.py` and connect at the bottom of that module with a `dispatch_uid`,
without which double-registration produces duplicate side effects:

```python
post_save.connect(on_foo_saved, sender=Foo, dispatch_uid="baseapp_foo_on_foo_saved")
```

Blocks may also define their own `Signal()` instances for other blocks to subscribe to —
`baseapp_comments/signals.py` defines `comment_created` / `comment_deleted`. Cross-block events go
through Django signals, never direct imports.

`baseapp_core.signals.document_created` fires when any `DocumentId` is created — the hook for
setting up a sidecar row for a newly documentable object.

## Anti-patterns

- Overriding `ready()` without `super().ready()`. Services and interfaces silently never register.
- Module-level imports of models, services, or GraphQL types in `apps.py`.
- Declaring a mixin but not implementing its method, or the reverse — implementing
  `register_shared_services` without inheriting `ServicesContributor`, so it is never called.
- Connecting a receiver without `dispatch_uid`.
- Importing another block directly to react to its events. Use a signal or a shared service.
- Setting `label` to the dotted form. It must be the underscore form.
- A bare `verbose_name = "BaseApp Foo"`. It is a user-facing admin label; `AGENTS.md` requires
  `gettext_lazy` for it by name.
