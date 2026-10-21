# BaseApp Notifications

Reusable app to have in-app notifications integrated with email and push notifications. Its built on top of [django-notifications-hq](https://github.com/django-notifications/django-notifications).

Based on the [Activity Streams Spec](http://activitystrea.ms/specs/atom/1.0/).

Notifications are actually actions events, which are categorized by four main components.

- `Actor`. The object that performed the activity.
- `Verb`. The verb phrase that identifies the action of the activity.
- `Action Object`. *(Optional)* The object linked to the action
itself.
- `Target`. *(Optional)* The object to which the activity was
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

- Finish implementing push notifications
- DRF views and serializers

## How to install:

Install the package with `pip install baseapp-backend[notifications]`.

If you want to develop, [install using this other guide](#how-to-develop).

## Setup In-App notifications

1 - Add to your `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
  "baseapp_notifications",
]
```

2 - Set the notification and notification settings model in your `settings/base.py`:

```python
NOTIFICATIONS_NOTIFICATION_MODEL = "notifications.Notification"
BASEAPP_NOTIFICATIONS_NOTIFICATIONSETTING_MODEL = "baseapp_notifications.NotificationSetting"
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
from baseapp_core.graphql import DjangoObjectType, Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces

class UserNode(DjangoObjectType):
    class Meta:
        interfaces = graphql_shared_interfaces.get(RelayNode, "NotificationsInterface")
```

5 - Make sure your graphql.py main file is loading queries, mutations and subscriptions from plugin_registry.

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

3 - Make sure your `urls.py` main file loads routes from the plugin_registry. The following push-notifications endpoints will be loaded automatically when `push_notifications` is installed:
- "push-notifications/apns": push_notifications.api.rest_framework.APNSDeviceAuthorizedViewSet
- "push-notifications/gcm": push_notifications.api.rest_framework.GCMDeviceAuthorizedViewSet
- "push-notifications/wns": push_notifications.api.rest_framework.WNSDeviceAuthorizedViewSet
- "push-notifications/web": push_notifications.api.rest_framework.WebPushDeviceAuthorizedViewSet

## How to send a notification

```python
from baseapp_core.plugins import shared_services

if service := shared_services.get("notifications"):
    service.send_notification(
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
- **recipient**: A **User**, a list/tuple/set or **QuerySet** of users, or an auth **Group**. Each recipient's notification settings are checked separately. (Required)
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

**Where a notification links to**: pass `url="/path/to/item"`; it is stored in `Notification.data["url"]`. This is the convention clients use for "where clicking the notification goes", so prefer it over custom keys.

Push notifications are queued with `transaction.on_commit`: inside a transaction they are sent after it commits, and not at all if it rolls back. In tests, wrap the call in `django_capture_on_commit_callbacks(execute=True)` (pytest-django) or `TestCase.captureOnCommitCallbacks(execute=True)` to assert on the push task.

## Email notifications

To send email notifications make sure to set `send_email=True` argument and `notification_url` so users can open the notification in the browser. The `description` will be used both as email's subject and email's body by default, check how to customize bellow.

```python
from baseapp_core.plugins import shared_services

if service := shared_services.get("notifications"):
    service.send_notification(
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

### How to replace the email sender

By default emails are rendered from the `.j2` templates above and sent with `send_mail`. To send them another way (a templated-email service, an outbox model, ...), point `BASEAPP_NOTIFICATIONS_EMAIL_SENDER` at a callable:

```python
# settings.py
BASEAPP_NOTIFICATIONS_EMAIL_SENDER = "apps.notifications.emails.send_notification_email"
```

```python
# apps/notifications/emails.py
def send_notification_email(recipient, notification, **context):
    # notification is the in-app Notification, or None when add_to_history=False or in-app is muted.
    # context holds sender, verb, description, action_object, target, email_subject,
    # email_message, add_to_history, send_push and every extra kwarg passed to send_notification.
    ...
    return True  # return False when nothing was sent, so the notification is not marked emailed
```

The default is `baseapp_notifications.utils.send_notification_email`.

## Notification groups

Groups turn raw verbs into user-facing preferences ("Comments", "Billing", "Security alerts"). Register them from your `AppConfig.ready()`:

```python
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CommentsConfig(AppConfig):
    name = "apps.comments"

    def ready(self):
        from baseapp_notifications.groups import register_notification_group

        # owns "comments" and every "comments.*" verb
        register_notification_group(
            "comments",
            label=_("Comments"),
            description=_("Replies and mentions on your posts"),
        )
        # owns exactly these verbs, only shown to staff, email only
        register_notification_group(
            "moderation",
            label=_("Moderation"),
            verbs=["comments.reported", "profiles.reported"],
            audience=lambda user: user.is_staff,
            channels=["EMAIL"],
        )
        # always delivered, users cannot turn it off
        register_notification_group("security", label=_("Security"), is_locked=True)
```

`register_notification_group(key, *, label, description="", verbs=None, audience=None, is_locked=False, channels=None)`:

- **key**: stable identifier, stored as `NotificationSetting.verb` for the group's preferences.
- **verbs**: the verbs the group owns. `None` owns `key` and every `key.*` verb (the longest matching key wins, so `chats.mentions` beats `chats`); a list owns exactly those verbs.
- **audience**: `callable(user) -> bool` deciding who sees and may change the group. `None` means everyone. It does not restrict sending.
- **is_locked**: locked groups ignore every setting (including `_ALL_`) and cannot be changed through the API.
- **channels**: the channels users can configure, as `NotificationChannelTypes` members, values or names. Defaults to in-app, email and push.

Registering a key again replaces the group. Read the registry with `get_notification_group(key)`, `list_notification_groups(user=None)`, `get_notification_group_for_verb(verb)` and `is_registered_verb(verb)`, all in `baseapp_notifications.groups`.

How settings resolve: `can_user_receive_notification(user_id, verb, channel)` looks at the rows for the verb's first segment (as before), for `_ALL_` and, when the verb belongs to a group, for the group key. A missing row means allowed; any inactive row for the channel or for `ALL` mutes it. Verbs outside every group behave exactly as before.

To catch typos, set `BASEAPP_NOTIFICATIONS_REQUIRE_REGISTERED_VERBS = True`: `send_notification` then raises `ImproperlyConfigured` for a verb no group owns. It defaults to `False`.

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| `BASEAPP_NOTIFICATIONS_EMAIL_SENDER` | `"baseapp_notifications.utils.send_notification_email"` | Dotted path to `callable(recipient, notification, **context)` that sends notification emails. |
| `BASEAPP_NOTIFICATIONS_REQUIRE_REGISTERED_VERBS` | `False` | Reject verbs that no registered notification group owns. |

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

Filter notifications by group (verb equal to the key or starting with `<key>.`, plus the explicit verbs of a registered group):

```graphql
query {
  me {
    notifications(group: "comments", unread: true) { edges { node { id verb data } } }
  }
}
```

List the groups the viewer can configure, with their state per channel:

```graphql
query {
  me {
    notificationSettingGroups {
      key
      label
      description
      isLocked
      channels { channel isActive }
    }
  }
}
```

### Mutations

```graphql
mutation {
  notificationsMarkAllAsRead(input: { read: true }) {
    recipient { notificationsUnreadCount }
  }

  notificationsMarkAsRead(input: { notificationIds: ["b3b6c8e2-8f2a-4e3a-9c1d-2f7e6a1b2c3d", "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"], read: true }) {
    recipient { notificationsUnreadCount }
  }
}
```

Set group preferences with `notificationSettingsUpdate`. It sets values (never toggles), so repeating it is safe. `channel: ALL` sets every channel of the group. The whole input is rejected with `errors` when an entry names an unknown group (or one outside the viewer's audience), a locked group, or a channel the group does not offer. `groups` returns each changed group's resulting state.

```graphql
mutation {
  notificationSettingsUpdate(input: {
    settings: [
      { group: "comments", channel: EMAIL, isActive: false }
      { group: "billing", channel: ALL, isActive: true }
    ]
  }) {
    groups { key channels { channel isActive } }
    errors { field messages }
  }
}
```

`notificationSettingToggle(input: { verb, channel })` is unchanged.

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

## How to develop

General development instructions can be found in [main README](../README.md#how-to-develop).
