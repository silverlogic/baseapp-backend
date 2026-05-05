# BaseApp Follows

Reusable app to let any model follow / unfollow any other model.

`Follow.actor` and `Follow.target` are foreign keys to `DocumentId` (not `Profile`), so the same `followToggle` mutation can wire up Profile-to-Profile follows, Profile-to-{anything else} follows, etc., as long as both sides have a `DocumentId`.

## How to install:

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup:

1 - Add `baseapp_follows` to your project's `INSTALLED_APPS` and run `./manage.py migrate`:

``python
INSTALLED_APPS = [
    # ...
    "baseapp_follows",
    # ...
]
``

2 - Add `FollowsPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file (via the plugin registry, like the other BaseApp packages):

``python
AUTHENTICATION_BACKENDS = [
    # ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_follows"),
    # ...
]
``

3 - Make sure your `graphql.py` main file is loading queries, mutations and subscriptions from `plugin_registry`. The plugin contributes `FollowsMutations` (`followToggle`).

## How to use

You need to add `FollowsInterface` to any GraphQL `ObjectType` you want to be followable. The interface is registered as a shared interface, so you opt in by name — no direct cross-package import:

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

``python
from baseapp_core.graphql import DjangoObjectType, Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class MyModelObjectType(DjangoObjectType):
    class Meta:
        model = MyModel
        interfaces = graphql_shared_interfaces.get(
            RelayNode, "FollowsInterface"
        )
``

### Mutation

`followToggle` creates or removes a follow between an actor and a target:

``graphql
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
``

### Settings

Out-of-the-box settings — these come from the plugin and you only need to override them if you want to swap models:

``python
BASEAPP_FOLLOWS_FOLLOW_MODEL = "follows.Follow"
BASEAPP_FOLLOWS_FOLLOWABLEMETADATA_MODEL = "follows.FollowableMetadata"
``

### Service: `followable_metadata`

`baseapp_follows` registers a `followable_metadata` shared service in `apps.ready()` (mirrors `baseapp_comments`'s `commentable_metadata` service). Consumers can:

``python
from baseapp_core.plugins import shared_services

service = shared_services.get("followable_metadata")
if service:
    service.get_followers_count(obj)        # uses an annotation if present, else a fetch
    service.get_following_count(obj)
    service.get_or_create_metadata(obj)     # returns FollowableMetadata for obj
    service.annotate_queryset(qs)           # see below
``

`annotate_queryset(qs)` adds `_followable_followers_count` and `_followable_following_count` as `Subquery` annotations against `follows_followablemetadata`. Object types that implement `FollowsInterface` should call this in their `pre_optimization_hook` so per-row count resolution doesn't N+1. The Profile object type already does this — see [`baseapp_profiles/graphql/object_types.py`](../baseapp_profiles/graphql/object_types.py).

### Signals

`Follow.save()` and `Follow.delete()` recompute `followers_count` / `following_count` on the affected `FollowableMetadata` rows under a row lock so concurrent follows / unfollows don't race. There are no extra signals for projects to override.

## Permissions

You can inherit `baseapp_follows.permissions.FollowsPermissionsBackend` to customize permissions:

``python
from baseapp_follows.permissions import FollowsPermissionsBackend


class MyFollowsPermissionsBackend(FollowsPermissionsBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_follows.add_follow":
            return user_obj.is_authenticated and not user_obj.is_blocked
        return super().has_perm(user_obj, perm, obj)
``

Then in `AUTHENTICATION_BACKENDS` in your django settings, replace the plugin entry with your subclass:

``python
AUTHENTICATION_BACKENDS = [
    # ...
    # *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_follows"),
    "myapp.permissions.MyFollowsPermissionsBackend",
    # ...
]
``

## How to Develop

General development instructions can be found in the [main README](..#how-to-develop).

### Prerequisites When Activating `baseapp_follows`

Whenever you activate `baseapp_follows`, you need to create a corresponding app to implement the concrete models. We suggest creating an app at `apps/social/follows/`. Then, inside `apps/social/follows/models.py`, you must implement:

``python
from baseapp_follows.models import AbstractFollow, AbstractFollowableMetadata


class Follow(AbstractFollow):
    class Meta(AbstractFollow.Meta):
        pass


class FollowableMetadata(AbstractFollowableMetadata):
    class Meta(AbstractFollowableMetadata.Meta):
        pass
``

Then point swapper at these models so they replace the abstract ones:

``python
# In your settings.py or settings/base.py, add:
BASEAPP_FOLLOWS_FOLLOW_MODEL = "follows.Follow"
BASEAPP_FOLLOWS_FOLLOWABLEMETADATA_MODEL = "follows.FollowableMetadata"
``

### Migrating from a legacy schema

If your project still has the old `Follow` schema (Profile-FK actor/target, no `FollowableMetadata` table), `baseapp_follows.migration_helpers` ships two reusable `RunPython`-ready helpers — see how `testproject/follows/migrations/0004_backfill_documentids_and_seed_followable_metadata.py` chains them:

- `convert_follow_profile_fks_into_document_id_helper.migrate_follow_profile_fks_to_document_id` — remaps `Follow.actor_id` / `Follow.target_id` from Profile PKs to `DocumentId` PKs (with a reverse function for downgrades and an end-of-migration assert that every row resolves to a real `DocumentId`).
- `seed_followable_metadata_from_follows_helper.seed_followable_metadata_from_follows` — counts existing follows per actor / target `DocumentId` and seeds `FollowableMetadata` rows so `followersCount` / `followingCount` are accurate the moment the new schema goes live.
