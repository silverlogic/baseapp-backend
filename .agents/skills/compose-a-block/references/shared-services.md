# Shared Services and GraphQL Interfaces

Two runtime registries let blocks cooperate without importing each other. Both are populated in
`AppConfig.ready()` (see `app-config-wiring.md`) and both are **optional at the consumer end** —
the consuming block must work when the provider isn't installed.

| Need | Mechanism |
|---|---|
| Expose behaviour or data to other blocks | `shared_services` |
| Add fields to another block's ObjectType | `graphql_shared_interfaces` |
| React to something that happened | Django signals |
| Optional model field / GraphQL field | `apps.is_installed(...)` / `apply_if_installed(...)` |

## Shared services

### Provider

```python
from django.apps import apps
from django.db import models

from baseapp_core.plugins import SharedServiceProvider


class FooableMetadataService(SharedServiceProvider):
    """Service that provides fooable metadata for any object with a DocumentId."""

    @property
    def service_name(self) -> str:
        return "fooable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_foo")

    def get_foos_count(self, obj) -> int:
        if hasattr(obj, "_fooable_foos_count"):
            val = obj._fooable_foos_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.foos_count if metadata else 0

    def annotate_queryset(self, queryset) -> models.QuerySet:
        return self._get_model().annotate_queryset(queryset)
```

Naming convention: `<thing>able_metadata` for the metadata services, dotted for narrower lookups
(`blocks.lookup`). Registered in `apps.py` by instance — the registry reads `service_name` itself.

The `hasattr` fallback pattern in the getters is the read-through contract from
`annotate-queryset.md`: annotate and it's free, don't and it still works.

Services hold no state and resolve their models lazily via `swapper.load_model`.

### Consumer

**Always guard.** The walrus form is the house idiom:

```python
from baseapp_core.plugins import shared_services

if service := shared_services.get("fooable_metadata"):
    queryset = service.annotate_queryset(queryset)
```

Never `shared_services.get(...)` at module import time — accessors are wrapped in
`@require_django_ready` and will raise. Call inside functions, methods, and resolvers.

When absent, degrade to a sane default rather than raising:

```python
    def resolve_foos_count(root, info, **kwargs) -> int:
        if service := shared_services.get("fooable_metadata"):
            return service.get_foos_count(root)
        return 0
```

## GraphQL shared interfaces

### Provider

Register a **getter**, not the class, so the import stays deferred:

```python
# graphql/interfaces.py
def get_foos_interface() -> type["FoosInterface"]:
    from .object_types import FoosInterface

    return FoosInterface
```

```python
# apps.py
    def register_graphql_shared_interfaces(self, registry) -> None:
        from .graphql.interfaces import get_foos_interface

        registry.register("FoosInterface", get_foos_interface)
```

### Consumer

Opt in **by name**. Unregistered names are silently skipped, so a type can list interfaces from
blocks that may not be installed:

```python
class BaseCommentObjectType:
    class Meta:
        interfaces = graphql_shared_interfaces.get(
            RelayNode,
            CommentsInterface,
            PermissionsInterface,
            "ReactionsInterface",
            "MentionsInterface",
            "NodeActivityLogInterface",
        )
```

The first argument is the relay node base; the rest are class objects (for interfaces from this
block or a hard dependency) or **strings** (for optional ones). Use strings for anything optional —
that is the whole point.

Interfaces that carry their own `optimizer_hook` wiring need nothing from the consumer. See
`optimizer-hooks.md`, including the `Meta.model` requirement without which the AST walker skips the
fragment.

## `apply_if_installed`

For optional entries in a list — GraphQL `Meta.fields`, admin `list_display`, filter tuples:

```python
from baseapp_core.plugins import apply_if_installed

        fields = (
            "pk",
            "user",
            *apply_if_installed("baseapp_profiles", ["profile"]),
            "body",
        )
```

Returns a type-matched empty value when the app is absent.

## Testing the absent case

A block that degrades must be tested degrading. Use `with_disabled_apps` /
`with_disabled_apps_context` from `baseapp_core/plugins/tests/fixtures.py`, which strips apps from
`INSTALLED_APPS`, resets the plugin registry, and reloads. Convention is
`tests/integration/test_<thing>_without_<block>.py` — e.g.
`baseapp_comments/tests/integration/test_comment_create_without_baseapp_profiles.py`.

Add `baseapp_core/plugins/tests/fixtures.py` to the block's `tests/conftest.py`:

```python
from baseapp_core.graphql.testing.fixtures import *  # noqa
from baseapp_core.plugins.tests.fixtures import with_disabled_apps  # noqa: F401
from baseapp_core.tests.fixtures import *  # noqa
```

## Anti-patterns

- `shared_services.get(...)` at module level. Raises via `@require_django_ready`.
- Using the result without a `None` check.
- Raising when an optional service is missing instead of returning a default.
- Registering the interface class instead of a getter — re-couples the import.
- Passing an optional interface as a class object rather than a string, so the consuming block
  hard-fails when the provider is absent.
- Importing another block's service class directly to call it.
- Declaring an optional dependency in `plugin.py` and then using it unconditionally in code.
