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
# Whether the "comment created" notification is also sent by email.
BASEAPP_COMMENTS_NOTIFICATION_CREATED_EMAIL = True  # default True
# Whether the "reply created" notification is also sent by email.
BASEAPP_COMMENTS_NOTIFICATION_REPLY_EMAIL = True  # default True
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

### Restricting who sees comments on a target

By default anyone who can see a target can read its comments.
`BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS = False` hides the comments list and the subscription
from anonymous users, as before. To keep the comments of some targets private, for example
internal notes on a record, deny `baseapp_comments.view_target_comments` for that target (`obj` is
the target). The app label follows your swapped `Comment` model. The check is applied to every read
path:

- `CommentsInterface.comments` returns no comments and `commentsCount` returns zeros.
- `node(id)` / `comment(id)` of a comment returns `null`, because `view_comment` also requires
  `view_target_comments` on the comment's target.
- `onCommentChange(targetObjectId: ...)` joins no group, and every notification is checked again
  with `view_comment` for each subscriber, so a permission revoked after subscribing, or a
  subscriber of every comment (`view_all_comments`), does not receive it.

```python
import swapper

from baseapp_comments.permissions import CommentsPermissionsBackend

Comment = swapper.load_model("baseapp_comments", "Comment")


class MyCommentsPermissionsBackend(CommentsPermissionsBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_comments.view_target_comments" and isinstance(obj, Account):
            return user_obj.is_staff
        return super().has_perm(user_obj, perm, obj)
```

Django grants a permission when any backend does, so replace the default backend with your subclass
in `AUTHENTICATION_BACKENDS` (see above) instead of adding a second one.

To also hide comment counts and comment nodes from anonymous users, return
`user_obj.is_authenticated` for this permission.

When a comment is itself the target of comments (its replies), `obj` is that comment. If the
restricted targets allow replies, deny those too, for example by walking up with
`while isinstance(obj, Comment): obj = obj.target`, or refuse `reply_comment` on them.

### Keeping comment activity private

With `baseapp.activity_log` installed, `commentCreate`, `commentUpdate` and `commentPin` log their
activity as public, so anyone can list it in `activityLogs`, including the change diff of the
comment. Deny `baseapp_comments.publish_comment_activity` for a target (`obj` is the target) to keep
that activity private. It is checked only after the mutation's own permission checks pass, and is
granted by default. Restricted targets usually deny both permissions:

```python
class MyCommentsPermissionsBackend(CommentsPermissionsBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_comments.publish_comment_activity" and isinstance(obj, Account):
            return False
        return super().has_perm(user_obj, perm, obj)
```

## How to Develop

General development instructions can be found in the [main README](../README.md#how-to-develop).

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
