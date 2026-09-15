# BaseApp Blocks

Reusable app that lets one profile block/unblock another. Blocks are stored as actor → target `Profile` relations, and per-object blocker / blocking counts are kept on a decoupled `BlockableMetadata` row (one per `DocumentId`) so the blocked model never has to carry counter columns. Today blocks are wired for profiles, but the `DocumentId`-based metadata follows the plugin architecture so it can be extended to any documentable model.

## How to install

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

The package registers itself as a plugin (see `baseapp_blocks.plugin:BlocksPlugin`), so most wiring happens through the plugin registry.

1. Add `baseapp_blocks` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_blocks",
    # ...
]
```

2. Wire the auth backend slot — `BlocksPermissionsBackend` is contributed via the registry:

```python
AUTHENTICATION_BACKENDS = [
    # ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_blocks"),
    # ...
]
```

3. Make sure your project's `graphql.py` composes the schema via `plugin_registry.get_all_graphql_*()` so `BlocksMutations` (`blockToggle`) is picked up automatically.

4. Define the concrete models (see [models](#models)) and point the swapper settings at them:

```python
BASEAPP_BLOCKS_BLOCK_MODEL = "blocks.Block"
BASEAPP_BLOCKS_BLOCKABLEMETADATA_MODEL = "blocks.BlockableMetadata"
```

Run `./manage.py makemigrations` / `./manage.py migrate` after defining them.

## Models

Both models are abstract + swappable, and the package ships **no** concrete models or migrations — your project must subclass the abstracts in a local app and point the swapper settings at them.

| Abstract | Concrete reference | Purpose |
|---|---|---|
| `AbstractBlock` | `Block` | A block relation. `actor` / `target` are `Profile` FKs (`related_name` `blocking` / `blockers`); `user` records who created it. `unique_together (actor, target)`. |
| `AbstractBlockableMetadata` | `BlockableMetadata` | Per-object `blockers_count` / `blocking_count`, keyed by a `OneToOneField` to `DocumentId`. Decouples counters from the blocked model. |

Both inherit `DocumentIdMixin`, so any block object can be the target of mentions, comments, follows, etc. without extra wiring.

`Block.save()` / `Block.delete()` keep the metadata counts in sync automatically by calling the `blockable_metadata` shared service whenever a block is created or removed.

Minimal concrete definition:

```python
# myproject/blocks/models.py
from baseapp_blocks.models import AbstractBlock, AbstractBlockableMetadata


class Block(AbstractBlock):
    class Meta(AbstractBlock.Meta):
        pass


class BlockableMetadata(AbstractBlockableMetadata):
    class Meta(AbstractBlockableMetadata.Meta):
        pass
```

## GraphQL

### Mutations

| Field | Purpose |
|---|---|
| `blockToggle` | Toggle a block between an `actor` profile and a `target` profile. Creates the block if absent (and refuses to block yourself), deletes it if present. Returns the new `block` edge (or `blockDeletedId`), plus the refreshed `target` and `actor`. |

```graphql
mutation BlockButtonMutation($input: BlockToggleInput!) {
    blockToggle(input: $input) {
        block {
            node {
                id
            }
        }
        blockDeletedId
        target {
            id
            blockersCount
            isBlockedByMe
        }
        actor {
            id
            blockingCount
        }
    }
}
```

### Shared GraphQL interface

Blocks publishes one shared interface via the registry — consuming object types opt in by name instead of importing it directly:

```python
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class ProfileObjectType(DjangoObjectType):
    class Meta:
        interfaces = graphql_shared_interfaces.get(RelayNode, "BlocksInterface")
        model = Profile
```

When `baseapp_blocks` is installed the registry returns the real `BlocksInterface`; when it isn't, the call falls back to defaults so the type still works.

The interface exposes (all permission-gated):

- `blockers` / `blocking` — paginated `Block` connections.
- `blockersCount` / `blockingCount` — counts read from `BlockableMetadata`. Both ship a `query_optimizer` field-level hook so the counts are annotated on demand and never N+1.
- `isBlockedByMe(profileId)` — whether the current user (or the given profile) blocks this object.

### Permissions

`BlocksPermissionsBackend` resolves the following object-level permissions:

- `baseapp_blocks.add_block` / `baseapp_blocks.add_block_with_profile` — create a block (the latter checks `use_profile` on the acting profile).
- `baseapp_blocks.delete_block` — owner of the block, the acting profile, or a moderator.
- `baseapp_blocks.view_block-blockers` / `-blockers_count` / `-blocking` / `-blocking_count` — gate the interface fields above.

## Shared services

### Provided

Blocks registers two services in `apps.py.ready()`:

- **`blockable_metadata`** (`BlockableMetadataService`) — read/maintain blocker & blocking counts for any `DocumentId`-backed object: `get_metadata` / `get_or_create_metadata`, `get_blockers_count` / `get_blocking_count`, `recompute_blockers_count` / `recompute_blocking_count`, and `annotate_queryset` for bulk (non-GraphQL) callers. The GraphQL path attaches each count on demand via the interface's optimizer hooks.

  ```python
  from baseapp_core.plugins import shared_services

  if service := shared_services.get("blockable_metadata"):
      count = service.get_blockers_count(profile)
  ```

- **`blocks.lookup`** (`BlockLookupService`) — `exclude_blocked_from_foreign_queryset(queryset, info)`. Lets other apps (e.g. comments) drop rows authored by profiles the current user blocks or is blocked by. Call it *before* the query optimizer evaluates the queryset:

  ```python
  from baseapp_core.plugins import shared_services

  if service := shared_services.get("blocks.lookup"):
      queryset = service.exclude_blocked_from_foreign_queryset(queryset, info)
  ```

### Required packages

- `baseapp_profiles` — `Block.actor` / `Block.target` are `Profile` FKs and the `BlocksInterface` resolvers disambiguate by the current profile.

## Migrating an existing project to BlockableMetadata

Older projects inherited a `BlockableModel` mixin that added `blockers_count` / `blocking_count` columns directly on the blocked model (typically `Profile`). That mixin has been removed. To migrate:

1. Add a migration that creates the `BlockableMetadata` table for your project (mirror `testproject/blocks/migrations/0002_blockablemetadata.py`).
2. Add a follow-up migration that calls `migrate_legacy_block_counts_to_metadata(...)` from `baseapp_blocks.migration_helpers.convert_legacy_block_counts_to_metadata_helper`, passing your model's app label and name. Use `reverse_migrate_legacy_block_counts_from_metadata(...)` as the reverse code. After the data is moved, `RemoveField` the legacy columns.

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp-blocks
```

The `-e` flag means any change you make in the cloned repo files will be reflected in the project. Run the test suite from the backend root:

```bash
docker compose run --rm web pytest baseapp_blocks/
```
