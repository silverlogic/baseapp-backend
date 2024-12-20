# BaseApp Content Feed

Reusable app to create and view posts on a feed.

## Whats missing

- [ ] DRF views and serializers

## How to install:

This package requires to following packages to be installed:

- [baseapp-core\[graphql\]](../baseapp-core/baseapp_core/graphql/README.md)
- [baseapp-notifications](../baseapp-notifications/README.md)
- [baseapp-reactions](../baseapp-reactions/README.md)

And install the package with `pip install baseapp-content-feed`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup:

1 - **Make sure** to have [GraphQL websocket enabled](../baseapp-core/baseapp_core/graphql/README.md#enable-websockets) in your project

2 - Add `baseapp_content_feed` to your project's `INSTALLED_APPS` and run `./manage.py migrate` as any other django model:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_content_feed",
    # ...
]
```

3 - Expose `ContentFeedMutations`, and `ContentFeedQueries` in your GraphQL/graphene endpoint, like:

```python
from baseapp_content_feed.graphql.mutations import ContentFeedMutations
from baseapp_content_feed.graphql.queries import ContentFeedQueries

class Query(graphene.ObjectType, ContentFeedQueries):
    pass

class Mutation(graphene.ObjectType, ContentFeedMutations):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```

## How to develop

General development instructions can be found in [main README](..#how-to-develop).
