# BaseApp Comments

Reusable app to handle comments threads.

## How to install:

Install the package with `pip install baseapp-backend`.

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

3 - Add `CommentsPermissionsBackend` to the `AUTHENTICATION_BACKENDS` list in your django settings file.

```python
AUTHENTICATION_BACKENDS = [
    # ...
    *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_comments"),
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

5 - Make sure your graphql.py main file is loading queries, mutations and subscriptions from plugin_registry.

## How to use

You can customize some settings, bellow are the default values:

```python
BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS = True  # default True
BASEAPP_COMMENTS_ENABLE_GRAPHQL_SUBSCRIPTIONS = True  # default True
BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS = True  # default True
BASEAPP_COMMENTS_MAX_PINS_PER_THREAD = None  # default None
```

You need to make sure to add `CommentsInterface` to your ObjectType's interfaces like:

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
from baseapp_core.graphql import DjangoObjectType, Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces


class MyModelObjectType(DjangoObjectType):
    class Meta:
        model = MyModel
        interfaces = graphql_shared_interfaces.get(
            RelayNode, "CommentsInterface"
        )

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

Then in the `AUTHENTICATION_BACKENDS` in your django settings file, comment the plugin_registry insertion and add the new one to the list.

```python
AUTHENTICATION_BACKENDS = [
    # ...
    # *plugin_registry.get("AUTHENTICATION_BACKENDS", "baseapp_comments"),
    "myapp.permissions.MyCommentsPermissionsBackend",
    # ...
]

```

## How to Develop

General development instructions can be found in the [main README](..#how-to-develop).

### Prerequisites When Activating `baseapp_comments`

Whenever you activate `baseapp_comments`, you need to create a corresponding app to implement the concrete models. We suggest creating an app at `apps/social/comments/`. Then, inside `apps/social/comments/models.py`, you must implement:

```python
from baseapp_comments.models import AbstractComment, AbstractCommentableMetadata


class Comment(AbstractComment):
    class Meta(AbstractComment.Meta):
        pass


class CommentableMetadata(AbstractCommentableMetadata):
    class Meta(AbstractCommentableMetadata.Meta):
        pass
```

After that, use swapper to identify these models as the comment models. You can then customize these models as needed, but we strongly recommend reviewing any customizations with the current CoP members to determine if they are necessary.

```python
# In your settings.py or settings/base.py, add:
BASEAPP_COMMENTS_COMMENT_MODEL = "comments.Comment"
BASEAPP_COMMENTS_COMMENTABLEMETADATA_MODEL = "comments.CommentableMetadata"
```

### Overriding `pghistory` Events

If you need to modify the default `pghistory` events registered for the concrete Comment model (see where `pghistory_register_default_track` is used in `baseapp_comments/models.py`), you can use our custom decorator `baseapp_core.pghelpers.pghistory_register_track` as shown below:

```python
from baseapp_comments.models import AbstractComment
from baseapp_core.pghelpers import pghistory_register_track


@pghistory_register_track(
    pghistory.InsertEvent(),
    pghistory.UpdateEvent(),
    pghistory.DeleteEvent(),
    exclude=["reactions_count", "modified", "extra_field_1"],
)
class Comment(AbstractComment):
    class Meta(AbstractComment.Meta):
        pass
```
