# BaseApp Notifications

Reusable app to have in-app notifications integrated with email and push notifications. Its built on top of [django-notifications-hq](https://github.com/django-notifications/django-notifications).

Based on the [Activity Streams Spec](http://activitystrea.ms/specs/atom/1.0/).

Notifications are actually actions events, which are categorized by four main components.

-   `Actor`. The object that performed the activity.
-   `Verb`. The verb phrase that identifies the action of the activity.
-   `Action Object`. *(Optional)* The object linked to the action
    itself.
-   `Target`. *(Optional)* The object to which the activity was
    performed.

`Actor`, `Action Object` and `Target` are `GenericForeignKeys` to any
arbitrary Django object. An action is a description of an action that
was performed (`Verb`) at some instant in time by some `Actor` on some
optional `Target` that results in an `Action Object` getting
created/updated/deleted.

For example: [nossila](https://github.com/nossila/) `(actor)`
*opened* `(verb)` [pull request
18](https://github.com/silverlogic/baseapp-backend/pull/18)
`(action_object)` on
[baseapp-backend](https://github.com/silverlogic/baseapp-backend)
`(target)` 12 hours ago

## Whats missing
- [X] Finish implementing push notifications
- [ ] DRF views and serializers

## How to install

Requirements:
- **baseapp-core** >= 0.2.0
- **django-notifications-hq** >= 1.8
- **django-push-notifications >= 3.2.0

Run `pip install baseapp-notifications`
And make sure to add the frozen version to your `requirements/base.txt` file

If you want to develop, [install using this other guide](#how-to-develop).

## Setup In-App notifications

1 - Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
  "baseapp_notifications",
]
```

2 - Set the notification model in your `settings/base.py`:

```python
NOTIFICATIONS_NOTIFICATION_MODEL = "baseapp_notifications.Notification"
```

Check how to customize to your own model [bellow](#how-to-customize-notifications-model).

3 - Make sure to add the task routing for `send_push_notification`

```python
CELERY_TASK_ROUTES = {
    "baseapp_notifications.tasks.send_push_notification": {
        "exchange": "default",
        "routing_key": "default",
    },
}
```

4 - Make sure that your main `User`'s `DjangoObjectType` implements interface `NotificationsInterface`:

```python
from baseapp_core.graphql import DjangoObjectType
from baseapp_notifications.graphql.object_types import NotificationsInterface

class UserNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, NotificationsInterface)
```

5 - Then you can expose notification's mutations and subscriptions:

```python
import graphene

from baseapp_notifications.graphql.mutations import NotificationsMutations
from baseapp_notifications.graphql.subscriptions import NotificationsSubscription


class Query(graphene.ObjectType):
    me = graphene.Field(UserNode)

    def resolve_me(self, info):
        if info.context.user.is_authenticated:
            return info.context.user


class Mutation(graphene.ObjectType, NotificationsMutations):
    pass


class Subscription(graphene.ObjectType, NotificationsSubscription):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation, subscription=Subscription)
```

## Setup Push notifications (apple and google)

1 - Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
  "push_notifications"
]
```

2 - Set the push notifications settings in your `settings/base.py`:

```python
PUSH_NOTIFICATIONS_SETTINGS = {
  "FCM_API_KEY": "[your api key]",
  "APNS_CERTIFICATE": ["Absolute path to your APNS certificate file"],
  "APNS_TOPIC": ["Apple app ID"],
  "DEFAULT_CLOUD_MESSAGE_TYPE": "FCM",
  "UPDATE_ON_DUPLICATE_REG_ID": True/False,
  "APNS_USE_SANDBOX": True/False,
}
```

You can get more details about this settings dict at the [django-push-notifications oficial repository](https://github.com/jazzband/django-push-notifications?tab=readme-ov-file#settings-list).

3 - Set the push notification routes in your `router.py`

```python
from push_notifications.api.rest_framework import (  # noqa
    APNSDeviceAuthorizedViewSet,
    GCMDeviceAuthorizedViewSet,
    WNSDeviceAuthorizedViewSet,
    WebPushDeviceAuthorizedViewSet,
)
router.register(r"push-notifications/apns", APNSDeviceAuthorizedViewSet, basename="apns")
router.register(r"push-notifications/gcm", GCMDeviceAuthorizedViewSet, basename="gcm")
router.register(r"push-notifications/wns", WNSDeviceAuthorizedViewSet, basename="wns")
router.register(r"push-notifications/web", WebPushDeviceAuthorizedViewSet, basename="web")
```

## How to send a notification

```python
from baseapp_notifications import send_notification

send_notification(
    add_to_history=True,
    send_push=True,
    send_email=True,
    sender=user,
    recipient=user,
    verb="opened",
    action_object=pr,
    target=repository,
    level="info",
    description=_("{user_name} opened a pull request in {repository_name}").format(
      user_name=user.name,
      repository_name=repository.name
    ),
    push_title=_("title"),
    push_description=_("description"),
    extra={},
)
```

Arguments:

- **add_to_history**: A boolean (default=True). True to add this to your in-app notifications history. 
- **send_push**: A boolean (default=True). True to send push notification to user's devices.
- **send_email**: A boolean (default=True). True to send notification via email.
- **sender**: An object of any type. (Required)
- **recipient**: A **Group** or a **User QuerySet** or a list of **User**. (Required)
- **verb**: An string. (Required)
- **action\_object**: An object of any type. (Optional)
- **target**: An object of any type. (Optional)
- **level**: One of Notification.LEVELS (\'success\', \'info\', \'warning\', \'error\') (default=info). (Optional)
- **description**: An string. (Optional)
- **notification_url**: URL used in emails so users can open this notification's page. (Optional)
- **email_subject**: An string (default=description). This will override the email's subject message. (Optional)
- **email_message**: An string (default=description). This will override the email's body message. (Optional)
- **public**: An boolean (default=True). (Optional)
- **timestamp**: An tzinfo (default=timezone.now()). (Optional)
- **push_description**: A string. (Required). The "body" of your push notification
- **push_title**: A string. (Optional). This will override the Title of your notification (apple and google uses the name defined on your build files)
- **extra**: A dict with data of any type. (Optional)

**Extra data**: ou can also send any arbitrary kwargs and they will be added to `Notification.data` JSONField.

## Email notifications

To send email notifications make sure to set `send_email=True` argument and `notification_url` so users can open the notification in the browser. The `description` will be used both as email's subject and email's body by default, check how to customize bellow.

```python
send_notification(
    sender=user,
    recipient=user,
    verb="opened",
    description="email's subject",
    add_to_history=True,
    send_email=True,
    notification_url="https://github.com/silverlogic/baseapp-backend/pull/18",
)
```

### How to customize email notification templates

By default it will look for templates based in your `slugify(verb)`, so can implement the following files with the following content in your project for each verb you want to customize:

Create `templates/emails/notifications/{verb_slugified}-subject.txt.j2` with:

```jinja2
{% include "emails/notification-subject.txt.j2" %}
```

Create `templates/emails/notifications/{verb_slugified}-body.txt.j2` with:

```jinja2
{% extends "emails/notification-body.txt.j2" %}
```

Create `templates/emails/notifications/{verb_slugified}-body.html.j2` with:

```jinja2
{% extends "emails/notification-body.html.j2" %}
```

You can copy the extended templates over to your project to customize them as well.

Also check [their source code in this repository](baseapp_notifications/templates/emails/) to understand how you can customize the notification message for each notification's verb, for example, to customize the email notification message (defaults to what you passed to `description`):

#### Example

```jinja2
{# templates/emails/notifications/opened-body.html.j2 #}
{% extends "emails/notification-body.html.j2" %}

{% block notification_message %}
    {{ recipient.name }}'s custom notification message.
{% endblock %}
```

## Public API documentation

In you GraphQL schema it will expose the following queries, mutations and subscriptions. Please check your GraphiQL playground for better understanding

### Queries

```graphql
query {
  me {
    notificationsUnreadCount
    notifications
  }
}
```

### Mutations

```graphql
mutation {
  notificationsMarkAllAsRead(input: { read: true }) {
    recipient { notificationsUnreadCount }
  }

  notificationsMarkAsRead(input: { notificationIds: ["Tm90aWZpY2F0aW9uOjE=", "Tm90aWZpY2F0aW9uOjI="], read: true }) {
    recipient { notificationsUnreadCount }
  }
}
```

### Subscriptions

```graphql
subscription {
  onNotificationChange {
    createdNotification @prependEdge(connections: $connections) {
      node {
        ...NotificationCardFragment

        recipient {
          id
          notificationsUnreadCount
        }
      }
    }

    updatedNotification {
      ...NotificationCardFragment
    }

    deletedNotificationId @deleteRecord
  }
}
```

## How to customize Notification's Model

Create your `custom_notifications` django app inside your project and inherit from `AbstractNotification` like:

```python
from baseapp_notifications.base import AbstractNotification

class Notification(AbstractNotification):
  my_custom_field = models.CharField()

  class Meta(AbstractNotification.Meta):
        abstract = False
```

Then make sure to change your `settings/base.py` like:

```python
INSTALLED_APPS = [
  "baseapp_notifications",
  "custom_notifications", # need to have both
]

NOTIFICATIONS_NOTIFICATION_MODEL = "custom_notifications.Notification"
```

That's it, `my_custom_field` should be available in your GraphQL's Notification ObjectType as well.

## How to develop

General development instructions can be found in [main README](..#how-to-develop).
