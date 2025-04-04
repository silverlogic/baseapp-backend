# BaseApp Comments

Reusable app to handle comments threads.

## Whats missing

- [ ] DRF views and serializers

## How to install:

This package requires to following packages to be installed:

- [baseapp-core\[graphql\]](../baseapp-core/baseapp_core/graphql/README.md)
- [baseapp-notifications](../baseapp-notifications/README.md)
- [baseapp-reactions](../baseapp-reactions/README.md)

And install the package with `pip install baseapp-comments`.

If you want to develop, [install using this other guide](#how-to-develop).

## How to setup:

1 - **Make sure** to have [GraphQL websocket enabled](../baseapp-core/baseapp_core/graphql/README.md#enable-websockets) in your project

2 - Add `baseapp_comments` to your project's `INSTALLED_APPS` and run `./manage.py migrate` as any other django model:

```python
INSTALLED_APPS = [
    # ...
    "baseapp_comments",
    # ...
]
```

3 - Add `baseapp_comments.permissions.CommentsPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file.

```python
AUTHENTICATION_BACKENDS = [
    # ...
    "baseapp_comments.permissions.CommentsPermissionsBackend",
    # ...
]
```

4 - Make sure to add the task routing for the notifications:

```python
CELERY_TASK_ROUTES = {
    "baseapp_comments.notifications.send_reply_created_notification": {
        "exchange": "default",
        "routing_key": "default",
    },
    "baseapp_comments.notifications.send_comment_created_notification": {
        "exchange": "default",
        "routing_key": "default",
    }
}
```

5 - Expose `CommentsMutations`, `CommentsQueries` and `CommentsSubscriptions` in your GraphQL/graphene endpoint, like:

```python
from baseapp_comments.graphql.mutations import CommentsMutations
from baseapp_comments.graphql.queries import CommentsQueries
from baseapp_comments.graphql.subscriptions import CommentsSubscriptions

class Query(graphene.ObjectType, CommentsQueries):
    pass

class Mutation(graphene.ObjectType, CommentsMutations):
    pass

class Subscription(graphene.ObjectType, CommentsSubscriptions):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
```

## How to use

You can customize some settings, bellow are the default values:

```python
BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS = True
BASEAPP_COMMENTS_MAX_PINS_PER_THREAD = None
BASEAPP_COMMENTS_ENABLE_GRAPHQL_SUBSCRIPTIONS = True
BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS = True
```

You need to inherit `CommentableModel` in your model and make sure to add `CommentsInterface` to your ObjectType's interfaces like:

### CommentableModel

```python
from django.db import models
from baseapp_comments.models import CommentableModel

class MyModel(models.Model, CommentableModel):
    pass
```

This will add the following fields to your model:

- `comments` a reverse relation to `Comment` model
- `comments_count` a JSON field that stores the count of comments for the object like: `{total: 5, main: 3, replies: 2, pinned: 1}`
- `is_comments_enabled` a boolean fields that stores if comments are enabled for the object

**Don't forget** to run `./manage.py makemigrations` and `./manage.py migrate` after adding `CommentableModel` to your model.

### CommentsInterface

`CommentsInterface` is a GraphQL interface that can be used to query for comments. It has the following fields:

- `isCommentsEnabled` return the active `URLPath`
- `commentsCount` return `CommentsCount` objectType with the following fields:
    - `total`
    - `main`
    - `replies`
    - `pinned`
- `comments` list of comments attached to this object

```python
from baseapp_core.graphql import DjangoObjectType
from baseapp_comments.graphql import CommentsInterface


class MyModelObjectType(DjangoObjectType):
    class Meta:
        model = MyModel
        interfaces = (relay.Node, CommentsInterface)

```

### Signals

There are some signals that handles stuff like updating comments count, notify users when a comment is created and send a GraphQL subscription when a comment is created, updated or deleted. You can find all signals in `baseapp_comments.signals`.

You could disconnect the signals and connect your own handlers if you want to customize the behavior.

```python
import swapper
from django.db.models.signals import post_save
from baseapp_comments.signals import notify_on_comment_created

Comment = swapper.load_model("baseapp_comments", "Comment")

post_save.disconnect(notify_on_comment_created, dispatch_uid="notify_on_comment_created")


def my_custom_notify_on_comment_created(sender, instance, created, **kwargs):
    # your custom code here
    pass
post_save.connect(notify_on_comment_created, sender=Comment, dispatch_uid="notify_on_comment_created")
```

## Permissions

In can inherit `baseapp_comments.permissions.CommentsPermissionsBackend` to customize the permissions.

```python
from baseapp_comments.permissions import CommentsPermissionsBackend


class MyCommentsPermissionsBackend(CommentsPermissionsBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_comments.add_comment_with_profile":
            return obj.owner_id == user.id  # only the profile's owner can use

        return super().has_perm(user_obj, perm, obj)
```

And add it to your `AUTHENTICATION_BACKENDS` list in your django settings file.

```python
AUTHENTICATION_BACKENDS = [
    # ...
    "myapp.permissions.MyCommentsPermissionsBackend",
    # ...
]

```

## How to develop

General development instructions can be found in [main README](..#how-to-develop).


## Breaking Changes
### [0.3.0] - 2024-10-23
- Removed pghistory tracking from the `Comment` model:

```python
@pghistory.track(
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
    exclude=["comments_count", "reactions_count"],
)

```
