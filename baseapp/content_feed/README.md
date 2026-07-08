# BaseApp Content Feed

Reusable app for a simple content feed: text posts (`ContentPost`) authored by a user / profile, each with any number of attached images (`ContentPostImage`). Reactions and @-mentions are layered in optionally through the plugin architecture, so the feed works on its own and gains those features automatically when the matching packages are installed.

## How to install

Install the package with `pip install baseapp-backend`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup

The package registers itself as a plugin (see `baseapp.content_feed.plugin:ContentFeedPlugin`), so the GraphQL wiring happens through the plugin registry.

1. Add `baseapp.content_feed` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "baseapp.content_feed",
    # ...
]
```

2. Make sure your project's `graphql.py` composes the schema via `plugin_registry.get_all_graphql_*()` so `ContentFeedQueries` (`contentPost`, `contentPosts`) and `ContentFeedMutations` (`contentPostCreate`) are picked up automatically.

3. Define the concrete models (see [models](#models)) and point the swapper settings at them:

```python
BASEAPP_CONTENT_FEED_CONTENTPOST_MODEL = "content_feed.ContentPost"
BASEAPP_CONTENT_FEED_CONTENTPOSTIMAGE_MODEL = "content_feed.ContentPostImage"
```

Run `./manage.py makemigrations` / `./manage.py migrate` after defining them.

## Models

Both models are abstract + swappable, and the package ships **no** concrete models or migrations — your project must subclass the abstracts in a local app and point the swapper settings at them.

| Abstract | Concrete reference | Purpose |
|---|---|---|
| `AbstractContentPost` | `ContentPost` | A feed post: `user` (author), `content` text, timestamps. When `baseapp_profiles` is installed, a `profile` FK (`related_name` `content_posts`) is mixed in. |
| `AbstractContentPostImage` | `ContentPostImage` | An image attached to a post via the `post` FK (`related_name` `images`). |

Both inherit `DocumentIdMixin`, so any post / image can be the target of mentions, comments, reactions, etc. without extra wiring.

Minimal concrete definition:

```python
# myproject/content_feed/models.py
from baseapp.content_feed.models import AbstractContentPost, AbstractContentPostImage


class ContentPost(AbstractContentPost):
    class Meta(AbstractContentPost.Meta):
        pass


class ContentPostImage(AbstractContentPostImage):
    class Meta(AbstractContentPostImage.Meta):
        pass
```

## GraphQL

### Queries

| Field | Description |
|---|---|
| `contentPost(id)` | RelayNode fetch of a single post by relay id. |
| `contentPosts` | Filterable connection of posts. Supports `orderBy: created` via `ContentPostFilter`. |

### Mutations

| Field | Purpose |
|---|---|
| `contentPostCreate` | Create a post from the current user (and current profile, if `baseapp_profiles` is installed). Accepts `content`, `isReactionsEnabled`, optional `mentionedProfileIds`, and uploaded `images` files. |

`contentPostCreate` runs in a transaction: it persists the post, sets the reactions-enabled flag through the `reactable_metadata` service, creates each validated `ContentPostImage`, and records mentions through the `mentions` service.

### Shared GraphQL interfaces

`ContentPostObjectType` opts into shared interfaces by name (they degrade gracefully when the providing package is absent):

```python
interfaces = graphql_shared_interfaces.get(
    RelayNode, "MentionsInterface", "ReactionsInterface"
)
```

- `MentionsInterface` (from `baseapp_mentions`) — exposes the post's mentions.
- `ReactionsInterface` (from `baseapp_reactions`) — exposes `reactionsCount` / `isReactionsEnabled` / `reactions`. `ContentPostObjectType.get_queryset` annotates the reactable metadata up front so these resolvers don't N+1.

## Shared services

### Consumed

Content Feed consumes the following services lazily via `shared_services.get(...)` — they are all optional, behaviour degrades gracefully when absent:

- `reactable_metadata` (from `baseapp_reactions`) — `set_is_reactions_enabled` on create and `annotate_queryset` when resolving the feed.
- `mentions` (from `baseapp_mentions`) — `update_mentions` to track inline @-mentions in post content.

### Optional packages

- `baseapp_profiles` — when installed, `ContentPost` exposes the authoring `profile` and `contentPostCreate` sets it from the current profile.
- `baseapp_reactions` — per-post reactions count / enabled flag via `ReactableMetadataService` and `ReactionsInterface`.
- `baseapp_mentions` — inline @-mention tracking on `contentPostCreate`.

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend
```

The `-e` flag means any change you make in the cloned repo files will be reflected in the project. Run the test suite from the backend root:

```bash
docker compose run --rm web pytest baseapp/content_feed/
```
