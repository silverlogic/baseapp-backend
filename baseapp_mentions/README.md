# BaseApp Mentions

Reusable app to let any model record mentioned profiles.

`Mention.target` is a foreign key to `DocumentId` (not the consuming model), so the same through-table can store mentions for Comments, Chat Messages, Content Posts, or any other model that has a `DocumentId` — no per-consumer M2M field or migration required.

## How to install:

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup:

1 - Add `baseapp_mentions` to your project's `INSTALLED_APPS` and run `./manage.py migrate`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_mentions",
    # ...
]
```

2 - Make sure your `graphql.py` main file is loading queries, mutations and subscriptions from `plugin_registry`. The plugin contributes the `MentionsInterface` shared interface and the `mentions` / `mentionable_metadata` shared services — consumer mutations call into the services rather than importing this package directly.

3 - `baseapp_mentions` requires `baseapp_profiles` to be installed (mentions point at a `Profile` foreign key). The plugin declares this in `required_packages` so misconfigurations surface at startup.

## How to use

### MentionsInterface

`MentionsInterface` is a GraphQL interface that exposes mention data for the implementing object. It is registered as a shared interface, so you opt in by name — no direct cross-package import:

```python
from baseapp_core.graphql import DjangoObjectType, Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class MyModelObjectType(DjangoObjectType):
    class Meta:
        model = MyModel
        interfaces = graphql_shared_interfaces.get(
            RelayNode, "MentionsInterface"
        )
```

The consuming model must expose a `document` `GenericRelation` to `baseapp_core.DocumentId` so the optimizer can walk `document__mentions` as a real Django prefetch path. `DocumentIdMixin` already declares it, so any consumer that inherits the mixin gets this for free.

Fields:

- `mentions` — `Connection<Mention>` over rows whose `target` resolves to this object's `DocumentId`. Each `Mention` node exposes `id`, `pk`, `created`, `modified`, `profile`, and `target`.
- `mentionsCount` — `Int`, count of mentions for this object. Served from a correlated subquery annotation attached on demand by `MentionableMetadataService` when the field is selected.
- `isMentioningProfile(profileId: ID!)` — `Boolean`, true when the given profile is mentioned in this object.

All optimizer wiring lives on the interface fields themselves — consumers do **not** need to add anything to their own `pre_optimization_hook`. Each field carries an `optimizer_hook` that registers the necessary annotation or prefetch only when the field is selected, so queries that ignore mentions pay nothing.

### Writing mentions from consumer mutations — `mentions` service

Consumer mutations (`commentCreate`, `commentUpdate`, `chatRoomSendMessage`, `chatRoomEditMessage`, `contentPostCreate`, ...) write mentions by calling the `mentions` shared service. The service is the single public seam; consumers never import this package directly:

```python
from baseapp_core.plugins import shared_services

service = shared_services.get("mentions")
if service:
    service.update_mentions(
        target_obj,                        # any DocumentId-aware model instance
        mentioned_profile_ids,             # iterable of Profile Relay IDs from the mutation input
        exclude_profile=current_profile,   # optional, drops self-mention
    )
```

`update_mentions` has `m2m.set(...)` semantics: it inserts new rows, deletes removed rows, and leaves unchanged rows untouched. It fires the `mentions_changed` signal once per call (batched) with the added / removed profile pks, and serializes concurrent callers writing the same target via a `select_for_update` lock on the target's `DocumentId` row so the replace semantics survive overlapping requests.

Mutations should treat `mentionedProfileIds` as follows:

- **Create**: write mentions if a list (including `[]`) is provided; no-op when the field is omitted.
- **Update**: an explicit list (including `[]`, which clears all mentions) replaces the set. `None` (field omitted) preserves the existing mentions.

The service also exposes `resolve_mentioned_profiles(ids, exclude_profile=None)` as a static helper if you need the resolved `Profile` instances without writing rows (e.g. to look up notification recipients).

### Reading counts efficiently — `mentionable_metadata` service

`baseapp_mentions` registers a `mentionable_metadata` shared service so non-GraphQL callers (REST views, admin, management commands) can read counts without N+1'ing the through-table:

```python
from baseapp_core.plugins import shared_services

service = shared_services.get("mentionable_metadata")
if service:
    service.get_mentions_count(obj)         # uses an annotation if present, else a fetch
    service.annotate_queryset(qs)           # adds _mentions_count + _mention_target_doc_id
```

GraphQL resolvers go through `MentionsInterface` and get the annotation for free via the field-level `optimizer_hook` — there's nothing to wire up in the consuming object type. `annotate_queryset` is for callers outside the GraphQL path.

### Signals

`baseapp_mentions.signals.mentions_changed` fires once per `update_mentions` call (only when the delta is non-empty) with:

- `sender` — the `Mention` model class
- `target` — the consuming object (Comment, Message, ContentPost, ...)
- `added` — list of newly mentioned profile pks
- `removed` — list of profile pks that lost their mention

Connect a receiver in your project to fan out notifications, write activity log entries, etc.:

```python
from django.dispatch import receiver
from baseapp_mentions.signals import mentions_changed


@receiver(mentions_changed)
def notify_mentioned_profiles(sender, target, added, removed, **kwargs):
    # your custom notification / activity logic
    pass
```

### Settings

Out-of-the-box settings — these come from the plugin and you only need to override them if you want to swap the model:

```python
BASEAPP_MENTIONS_MENTION_MODEL = "mentions.Mention"
```

## How to Develop

General development instructions can be found in the [main README](..#how-to-develop).

### Prerequisites When Activating `baseapp_mentions`

Whenever you activate `baseapp_mentions`, you need to create a corresponding app to implement the concrete model. We suggest creating an app at `apps/social/mentions/`. Then, inside `apps/social/mentions/models.py`, you must implement:

```python
from baseapp_mentions.models import AbstractBaseMention


class Mention(AbstractBaseMention):
    class Meta(AbstractBaseMention.Meta):
        pass
```

Then point swapper at the concrete model so it replaces the abstract one:

```python
# In your settings.py or settings/base.py, add:
BASEAPP_MENTIONS_MENTION_MODEL = "mentions.Mention"
```
