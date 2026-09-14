# BaseApp Reactions

Reusable app to enable User's reactions on any model, features like like/dislike or any other reactions type, customizable for project's needs.

## How to install

```bash
pip install baseapp-backend
```

Add `baseapp_reactions` to `INSTALLED_APPS`. The package registers itself as a
plugin (see `baseapp_reactions.plugin:ReactionsPlugin`), so:

- `ReactionsQueries` / `ReactionsMutations` are contributed via
  `plugin_registry.get_all_graphql_queries()` / `get_all_graphql_mutations()`.
- `ReactionsPermissionsBackend` is contributed via
  `plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_reactions")`.
- The `ReactionsInterface` GraphQL interface is registered by name; consumers
  fetch it from `graphql_shared_interfaces` instead of importing it directly.
- A `reactable_metadata` shared service exposes
  `get_reactions_count(obj)` / `is_reactions_enabled(obj)` /
  `set_is_reactions_enabled(obj, value)` / `annotate_queryset(qs)` for any
  object that has a `DocumentId`. Consumers should use this service instead
  of inheriting from a mixin.

## How to use

### GraphQL — opt a type into reactions

Request the interface by name in your object type's `Meta.interfaces`:

```python
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class PostNode(DjangoObjectType):
    class Meta:
        interfaces = graphql_shared_interfaces.get(RelayNode, "ReactionsInterface")
```

When `baseapp_reactions` is installed the registry returns the real
`ReactionsInterface`; when it isn't, the call falls back to defaults so the
type still works.

### GraphQL — exposing the schema

Nothing to do. The plugin entry-point in `pyproject.toml` registers
`ReactionsQueries` and `ReactionsMutations`, and the project's root `Query` /
`Mutation` should already spread `*plugin_registry.get_all_graphql_queries()`
and `*plugin_registry.get_all_graphql_mutations()`. `reactionToggle` and the
`Reaction` node show up automatically.

Example query:

```graphql
{
    comment(id: $id) {
        id
        reactionsCount {
            LIKE
            DISLIKE
            total
        }
        isReactionsEnabled
        reactions(first: 10) {
            edges {
                node {
                    reactionType
                    user {
                        name
                    }
                }
            }
        }
    }
}
```

### Reading reaction counts on a model

Counts live on `ReactableMetadata` (one row per `DocumentId`), not on the
reacted-to model itself. Read them via the shared service:

```python
from baseapp_core.plugins import shared_services


service = shared_services.get("reactable_metadata")
counts = service.get_reactions_count(my_obj)        # dict, e.g. {"total": 3, "LIKE": 2, "DISLIKE": 1}
enabled = service.is_reactions_enabled(my_obj)      # bool, defaults to True

# Mutating: write the enabled flag through the service.
service.set_is_reactions_enabled(my_obj, False)
```

For querysets that will resolve `reactionsCount` for many rows, annotate up
front to avoid N+1:

```python
qs = service.annotate_queryset(qs)
```

`annotate_queryset` also adds a flat public `reactions_count_total` annotation
so consumer-side `OrderingFilter`s can sort on a real expression, e.g.:

```python
order_by = django_filters.OrderingFilter(
    fields=(("reactions_count_total", "reactions_count_total"),),
)
```

The `Reaction.save()` / `Reaction.delete()` hooks already maintain
`ReactableMetadata.reactions_count` for you whenever a reaction is added,
removed, or toggled.

### Settings

| Setting | Default | Description |
|---|---|---|
| `BASEAPP_REACTIONS_REACTION_MODEL` | `baseapp_reactions.Reaction` | Swappable concrete `Reaction` model. |
| `BASEAPP_REACTIONS_REACTABLEMETADATA_MODEL` | `baseapp_reactions.ReactableMetadata` | Swappable concrete metadata model. |
| `BASEAPP_REACTIONS_CAN_ANONYMOUS_VIEW_REACTIONS` | `True` | When `False`, `view_reaction` denies unauthenticated users. The legacy double-S typo `BASEAPP_REACTIONS_CAN_ANONYMOUS_VIEW_REACTIONSS` is honoured as a fallback for one release; please rename. |
| `BASEAPP_REACTIONS_ENABLE_NOTIFICATIONS` | `True` | When `True` (and `baseapp_notifications` is installed), `Reaction.save` fires a celery task that notifies the target's owner. |
| `BASEAPP_REACTIONS_NOTIFICATION_CREATED_EMAIL` | `True` | When `True` (and `baseapp_notifications` is installed), send_reaction_created_notification fires a created reaction email. |

## How to customise the Reaction / ReactableMetadata models

Define concrete models in your project that subclass the abstracts:

```python
# myproject/reactions/models.py
from baseapp_reactions.models import AbstractReactableMetadata, AbstractReaction


class Reaction(AbstractReaction):
    class Meta(AbstractReaction.Meta):
        pass


class ReactableMetadata(AbstractReactableMetadata):
    class Meta(AbstractReactableMetadata.Meta):
        pass
```

Add the new app to `INSTALLED_APPS`, run `makemigrations` / `migrate`, and
point the swapper settings at it:

```python
# settings.py
BASEAPP_REACTIONS_REACTION_MODEL = "reactions.Reaction"
BASEAPP_REACTIONS_REACTABLEMETADATA_MODEL = "reactions.ReactableMetadata"
```

Reaction supports custom reaction types by overriding `ReactionTypes` on your
concrete model:

```python
class Reaction(AbstractReaction):
    class ReactionTypes(models.IntegerChoices):
        LIKE = 1, _("like")
        DISLIKE = -1, _("dislike")
        LOVE = 2, _("love")
        FIRE = 3, _("fire")
```

`default_reactions_count()` reads `Reaction.ReactionTypes` lazily, so the
`ReactableMetadata.reactions_count` JSON dict picks up your new keys
automatically (`{"total": 0, "LIKE": 0, "DISLIKE": 0, "LOVE": 0, "FIRE": 0}`).

## Writing test cases in your project

`AbstractReactionFactory` helps you build factories for the swapped model:

```python
import factory
from baseapp_reactions.tests.factories import AbstractReactionFactory


class ReactionFactory(AbstractReactionFactory):
    target = factory.SubFactory(SomeTargetFactory)

    class Meta:
        model = "reactions.Reaction"   # or "baseapp_reactions.Reaction" if you didn't swap
```

## Migrating an existing project to ReactableMetadata

Older projects inherited a `ReactableModel` mixin that added `reactions_count`
and `is_reactions_enabled` columns directly on the reacted-to model. That
mixin has been removed. To migrate:

1. Add a migration that creates the `ReactableMetadata` table for your project
   (mirror `testproject/reactions/migrations/0002_reactablemetadata.py`).
2. Add a follow-up migration that calls
   `migrate_legacy_reactable_fields_to_metadata(...)` from
   `baseapp_reactions.migration_helpers.convert_legacy_reactable_fields_to_metadata_helper`,
   passing your model's app label and name. After the data is moved,
   `RemoveField` the legacy columns and recompile any pghistory triggers
   that reference them.
3. If you ever need to recompute counts from live `Reaction` rows, call
   `seed_reactable_metadata_from_reactions(...)` from
   `baseapp_reactions.migration_helpers.seed_reactable_metadata_from_reactions_helper`,
   or run the bundled management command:

   ```bash
   python manage.py update_reactions_count
   ```

## Migrating an existing project to ``target_document``

The `Reaction` model previously stored its target via a `GenericForeignKey`
over (`target_content_type`, `target_object_id`). It now stores it as
`target_document = ForeignKey(DocumentId)` for loose coupling. To migrate,
use `migrate_reaction_targets_to_document_id` from
`baseapp_reactions.migration_helpers.convert_reactions_gfk_into_document_id_helper`.
See `testproject/reactions/migrations/0003_convert_target_to_document.py` for
a complete example: AddField nullable → RunPython backfill → AlterField NOT
NULL → RemoveField on legacy GFK columns → re-add new index / unique_together.

## How to develop

Clone the monorepo into your backend directory:

```bash
git clone git@github.com:silverlogic/baseapp-backend.git
```

Then install editable:

```bash
pip install -e baseapp-backend
```
