# BaseApp Follows

Reusable app to let any model follow / unfollow any other model.

`Follow.actor` and `Follow.target` are foreign keys to `DocumentId` (not `Profile`), so the same `followToggle` mutation can wire up Profile-to-Profile follows, Profile-to-{anything else} follows, etc., as long as both sides have a `DocumentId`.

## How to install:

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup:

1 - Add `baseapp_follows` to your project's `INSTALLED_APPS` and run `./manage.py migrate`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_follows",
    # ...
]
```

2 - Add `FollowsPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file (via the plugin registry, like the other BaseApp packages):

```python
AUTHENTICATION_BACKENDS = [
    # ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_follows"),
    # ...
]
```

3 - Make sure your Strawberry schema is built from `plugin_registry.get_all_strawberry_*()` (see `testproject/graphql.py`). The plugin contributes `FollowsMutations` (`followToggle`) and the `Follow` type.

## How to use

You need to add `FollowsInterface` to any Strawberry type you want to be followable. The interface is registered as a shared interface, so you opt in by name — no direct cross-package import:

### FollowsInterface

`FollowsInterface` is a GraphQL interface that exposes follow data for the implementing object. Fields:

- `followersCount` — `Int`, served from `FollowableMetadata` (kept up to date by `Follow.save()` / `Follow.delete()`).
- `followingCount` — `Int`, same source.
- `followers` — `Connection<Follow>` over rows whose `target` is this object.
- `following` — `Connection<Follow>` over rows whose `actor` is this object.
- `isFollowedByMe(profileId: ID)` — `Boolean`, true when the current user (or the explicitly passed profile) follows this object.

Each `Follow` node exposes:

- `id`, `pk`, `created`, `modified`, `user`, `targetIsFollowingBack`
- `actor`, `target` — the `DocumentId` rows
- `actorObject`, `targetObject` — the resolved underlying model (Profile or anything else with a `DocumentId`), accessed through the GFK and a request-scoped cache.

```python
from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import Node, django_type


@django_type(MyModel)
class MyModelType(*strawberry_shared_interfaces.get("FollowsInterface"), Node):
    ...
```

### Mutation

`followToggle` creates or removes a follow between an actor and a target:

```graphql
mutation FollowButtonMutation($input: FollowToggleInput!) {
    followToggle(input: $input) {
        follow {
            node {
                id
            }
        }
        target {
            id
            followersCount
            isFollowedByMe
        }
        actor {
            id
            followingCount
        }
    }
}
```

### Settings

Out-of-the-box settings — these come from the plugin and you only need to override them if you want to swap models:

```python
BASEAPP_FOLLOWS_FOLLOW_MODEL = "follows.Follow"
BASEAPP_FOLLOWS_FOLLOWABLEMETADATA_MODEL = "follows.FollowableMetadata"
```

### Service: `followable_metadata`

`baseapp_follows` registers a `followable_metadata` shared service in `apps.ready()` (mirrors `baseapp_comments`'s `commentable_metadata` service). Consumers can:

```python
from baseapp_core.plugins import shared_services

service = shared_services.get("followable_metadata")
if service:
    service.get_followers_count(obj)        # uses an annotation if present, else a fetch
    service.get_following_count(obj)
    service.get_or_create_metadata(obj)     # returns FollowableMetadata for obj
    service.annotate_queryset(qs)           # see below
```

`annotate_queryset(qs)` adds `_followable_followers_count` and `_followable_following_count` as `Subquery` annotations against `follows_followablemetadata`. `FollowsInterface`'s count fields add the same annotations through strawberry-django optimizer hints (`get_annotations(model)`), so types implementing the interface don't N+1 without any extra wiring.

### How to read counts efficiently — `annotate_queryset` is the standard read path

Every read of `followers_count` / `following_count` should resolve from a queryset
annotation, NOT from `obj.followable_metadata.followers_count` per row.

**N+1 trap to avoid:**

```python
# ❌ One extra SELECT per profile — hits FollowableMetadata once per row.
for profile in Profile.objects.all():
    print(profile.followable_metadata.followers_count)
```

**The correct pattern:**

```python
from baseapp_core.plugins import shared_services

service = shared_services.get("followable_metadata")
qs = service.annotate_queryset(Profile.objects.all())
for profile in qs:
    # `_followable_followers_count` lands as a column on the SELECT — zero extra queries.
    print(profile._followable_followers_count, profile._followable_following_count)
```

GraphQL resolvers that go through `FollowsInterface` get this for free: the
`followersCount` / `followingCount` fields carry optimizer `annotate` hints, so the
annotation is added to whatever queryset the optimizer builds for the implementing type.

If you're reading counts outside GraphQL (REST, management commands, signals): always
go through `service.get_followers_count(obj)` / `service.get_following_count(obj)`.
Both helpers prefer the `_followable_*_count` annotation if present and fall back to a
single FollowableMetadata fetch otherwise — so they degrade gracefully when called on
an unannotated instance, but reward callers who pre-annotate the queryset.

### How counts are kept up to date

Every `Follow.save()` and `Follow.delete()` adjusts the matching `FollowableMetadata`
row via an atomic `F('field') + 1` / `F('field') - 1` UPDATE — no `COUNT(*)` and no
`SELECT FOR UPDATE` on the live path, so writes stay O(1) per follow regardless of
how many followers a target already has.

If counters drift (e.g. after a bulk insert that bypassed `save()`, or a botched
backfill), reconcile them with the matching classmethod:

```python
import swapper

Follow = swapper.load_model("baseapp_follows", "Follow")

Follow.recount_followers_count(target_doc_id)   # re-derives followers_count from row count
Follow.recount_following_count(actor_doc_id)    # re-derives following_count from row count
```

`recount_*` does take a row lock and a full `COUNT(*)` — fine for an offline
reconciliation job, **not** for the live request path.

### Pre-warming non-Profile follow targets

`AbstractFollowType.actorObject` / `targetObject` (in [`baseapp_follows/strawberry/types.py`](strawberry/types.py)) carry a `document_prefetch` optimizer hint: a `GenericPrefetch("content_object", […])` against the `actor` and `target` `DocumentId`s of every Follow row in a connection, so the objects resolve from a single batched fetch instead of one query per row. Out of the box that prefetch only includes `Profile` since profile-to-profile is the dominant case.

If your project lets users follow other entities (e.g. `Hive`, `Page`, `Organization`) and you query those connections at scale, override the type and pass the models to prefetch:

```python
# apps/social/follows/strawberry/types.py
from typing import Any, Optional

import strawberry_django
import swapper
from strawberry.types import Info

from baseapp_core.graphql import resolve_document_content_object
from baseapp_core.strawberry import Node, django_type
from baseapp_follows.filters import FollowsFilter
from baseapp_follows.strawberry.types import AbstractFollowType, document_prefetch

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")
Hive = swapper.load_model("hives", "Hive")


@django_type(Follow, filterset_class=FollowsFilter, relations=("user",))
class FollowType(AbstractFollowType, Node):
    @strawberry_django.field(
        graphql_type=Optional[Node],
        only=["actor_id"],
        prefetch_related=document_prefetch("actor", [Profile, Hive]),
    )
    def actor_object(self, info: Info) -> Any:
        return resolve_document_content_object(self.actor, info)

    @strawberry_django.field(
        graphql_type=Optional[Node],
        only=["target_id"],
        prefetch_related=document_prefetch("target", [Profile, Hive]),
    )
    def target_object(self, info: Info) -> Any:
        return resolve_document_content_object(self.target, info)
```

List the module in your plugin's `strawberry_types` (the last registration for a model wins).

**Notes:**

- Each model's queryset is its unfiltered default manager, optimized for the selection under the field. Django selects the rows by `(content_type_id, object_id)` itself.
- Only models you actually expect to be followed at meaningful volume need pre-warming. For the long tail of rare types, the request-scoped cache in `resolve_document_content_object` (in `baseapp_core.graphql.utils`) collapses lookups to **one DB hit per unique target**, not per follow row — so the cost stays bounded.
- Auto-discovery (e.g. inspecting the queryset to see which `content_type_id`s appear) isn't possible from an optimizer hint: the queryset is still lazy at that point. The list is intentionally project-declared.

### Signals

`Follow.save()` and `Follow.delete()` recompute `followers_count` / `following_count` on the affected `FollowableMetadata` rows under a row lock so concurrent follows / unfollows don't race. There are no extra signals for projects to override.

## Permissions

You can inherit `baseapp_follows.permissions.FollowsPermissionsBackend` to customize permissions:

```python
from baseapp_follows.permissions import FollowsPermissionsBackend


class MyFollowsPermissionsBackend(FollowsPermissionsBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_follows.add_follow":
            return user_obj.is_authenticated and not user_obj.is_blocked
        return super().has_perm(user_obj, perm, obj)
```

Then in `AUTHENTICATION_BACKENDS` in your django settings, replace the plugin entry with your subclass:

```python
AUTHENTICATION_BACKENDS = [
    # ...
    # *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_follows"),
    "myapp.permissions.MyFollowsPermissionsBackend",
    # ...
]
```

## How to Develop

General development instructions can be found in the [main README](../README.md#how-to-develop).

### Prerequisites When Activating `baseapp_follows`

Whenever you activate `baseapp_follows`, you need to create a corresponding app to implement the concrete models. We suggest creating an app at `apps/social/follows/`. Then, inside `apps/social/follows/models.py`, you must implement:

```python
from baseapp_follows.models import AbstractFollow, AbstractFollowableMetadata


class Follow(AbstractFollow):
    class Meta(AbstractFollow.Meta):
        pass


class FollowableMetadata(AbstractFollowableMetadata):
    class Meta(AbstractFollowableMetadata.Meta):
        pass
```

Then point swapper at these models so they replace the abstract ones:

```python
# In your settings.py or settings/base.py, add:
BASEAPP_FOLLOWS_FOLLOW_MODEL = "follows.Follow"
BASEAPP_FOLLOWS_FOLLOWABLEMETADATA_MODEL = "follows.FollowableMetadata"
```

### Migrating from a legacy schema

If your project still has the old `Follow` schema (Profile-FK actor/target, no `FollowableMetadata` table), `baseapp_follows.migration_helpers` ships two reusable `RunPython`-ready helpers — see how `testproject/follows/migrations/0004_backfill_documentids_and_seed_followable_metadata.py` chains them:

- `convert_follow_profile_fks_into_document_id_helper.migrate_follow_profile_fks_to_document_id` — remaps `Follow.actor_id` / `Follow.target_id` from Profile PKs to `DocumentId` PKs (with a reverse function for downgrades and an end-of-migration assert that every row resolves to a real `DocumentId`).
- `seed_followable_metadata_from_follows_helper.seed_followable_metadata_from_follows` — counts existing follows per actor / target `DocumentId` and seeds `FollowableMetadata` rows so `followersCount` / `followingCount` are accurate the moment the new schema goes live.
