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
- **email_template**: Base name of the email templates to use instead of the verb's (see [How to customize email notification templates](#how-to-customize-email-notification-templates)). (Optional)
- **email_context**: A dict added to the email's render context. Its keys override the other context values (`description`, `email_message`, extra kwargs, ...), except `notification`, `recipient` and `verb`, which it may not set. Model instances are fine: it is never stored. (Optional)
- **email_options**: A dict of delivery options for the email sender. The default sender reads `from_email`, `reply_to`, `cc`, `bcc` (a string or a list of addresses) and `attachments` (`(filename, content, mimetype)` tuples or MIME objects) and ignores other keys, so a custom sender can accept its own. (Optional)

`email_template`, `email_context` and `email_options` only reach the email sender. They are not stored in `Notification.data` and not sent to the push task. `send_notification` checks them before creating anything: an `email_context` that is not a dict or sets a reserved key, or `email_options` that are not a dict or whose `reply_to`, `cc` or `bcc` is not a string, list or tuple, raise `TypeError` or `ValueError` right away.

**Extra data**: ou can also send any arbitrary kwargs and they will be added to `Notification.data` JSONField.

**Where a notification links to**: pass `url="/path/to/item"`; it is stored in `Notification.data["url"]`. This is the convention clients use for "where clicking the notification goes", so prefer it over custom keys.

Push and email notifications are sent with `transaction.on_commit`: inside a transaction they go out after it commits, and not at all if it rolls back. Outside a transaction they are sent right away, as before, and an error from the email sender or the push queue reaches the caller. Inside a transaction an error is logged (logger `baseapp_notifications.services`) and not raised: the notifications are already committed, and raising would skip every later `on_commit` callback, such as the other recipients' email and push. `Notification.emailed` is set once the email has been sent, so it stays `False` when the sender failed. In tests, wrap the call in `django_capture_on_commit_callbacks(execute=True)` (pytest-django) or `TestCase.captureOnCommitCallbacks(execute=True)` to assert on the push task, `mail.outbox` or `emailed`.

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

An email has three parts: `{base}-subject.txt.j2`, `{base}-body.txt.j2` and `{base}-body.html.j2`. The base is picked in this order:

1. `email_template`, when passed to `send_notification`;
2. `emails/notifications/{verb}`, the raw verb with its dots (`emails/notifications/comments.reply-subject.txt.j2`);
3. `emails/notifications/{slugify(verb)}`, the older naming, which keeps working;
4. `emails/notification`, the generic templates of this package.

A base is used when at least one of its parts exists. Each part is taken from the first of these bases that has it, so a part the raw-verb templates lack comes from the slug templates, then from the generic ones (an `email_template` falls back to the generic parts only). Set `BASEAPP_NOTIFICATIONS_EMAIL_REQUIRE_VERB_TEMPLATE = True` to drop step 4: a verb without templates of its own (and no `email_template`) is then not emailed, and `Notification.emailed` stays `False`. That turns "this verb sends an email" into "this verb has a template".

Custom senders can apply the same rule with `resolve_notification_email_template(verb, template=None)` from `baseapp_notifications.utils`. It returns the first base name, or `None` when the verb must not be emailed. `get_notification_email_template_bases(verb, template=None)` returns every base in order (or `None`), for senders that fall back per part.

For each verb you want to customize, create the following files in your project:

Create `templates/emails/notifications/{verb}-subject.txt.j2` with:

```jinja2
{% include "emails/notification-subject.txt.j2" %}
```

Create `templates/emails/notifications/{verb}-body.txt.j2` with:

```jinja2
{% extends "emails/notification-body.txt.j2" %}
```

Create `templates/emails/notifications/{verb}-body.html.j2` with:

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

By default emails are rendered from the `.j2` templates above and sent with `EmailMultiAlternatives` (the default connection and `DEFAULT_FROM_EMAIL`, as `send_mail` did). To send them another way (a templated-email service, an outbox model, ...), point `BASEAPP_NOTIFICATIONS_EMAIL_SENDER` at a callable:

```python
# settings.py
BASEAPP_NOTIFICATIONS_EMAIL_SENDER = "apps.notifications.emails.send_notification_email"
```

```python
# apps/notifications/emails.py
def send_notification_email(recipient, notification, **context):
    # notification is the in-app Notification, or None when add_to_history=False or in-app is muted.
    # context holds sender, verb, description, action_object, target, email_subject,
    # email_message, add_to_history, send_push, email_template, email_context, email_options
    # and every extra kwarg passed to send_notification.
    ...
    return True  # return False when nothing was sent, so the notification is not marked emailed
```

The default is `baseapp_notifications.utils.send_notification_email`, which renders the templates through `baseapp_notifications.utils.send_email_notification`; patch that one in tests (`send_notification` no longer imports it into `baseapp_notifications.services`).

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

`register_notification_group(key, *, label, description="", verbs=None, audience=None, is_locked=False, channels=None, keep_verbs=False)`:

- **key**: stable identifier, stored as `NotificationSetting.verb` for the group's preferences.
- **verbs**: the verbs the group owns. `None` owns `key` and every `key.*` verb (the longest matching key wins, so `chats.mentions` beats `chats`); a list owns exactly those verbs.
- **audience**: `callable(user) -> bool` deciding who sees and may change the group. `None` means everyone. It does not restrict sending. If it raises, the error is logged and the group is hidden from that user.
- **is_locked**: locked groups ignore every setting (including `_ALL_`) and cannot be changed through the API.
- **channels**: the channels users can configure, as `NotificationChannelTypes` members, values or names. Defaults to in-app, email and push.
- **keep_verbs**: when the key is already registered with explicit `verbs`, keep those verbs after the new ones instead of replacing them. Needs an explicit `verbs` list.

Registering a key again replaces the group, unless `keep_verbs=True`.

Apps that add verbs to a group another app registered use `extend_notification_group(key, verbs)`:

```python
from baseapp_notifications.groups import extend_notification_group

extend_notification_group("moderation", ["events.reported"])
```

It appends the verbs (skipping ones the group already owns, so calling it again changes nothing) and keeps the group's place in the list. It raises `ImproperlyConfigured` for an unknown key or a group registered without `verbs`, which already owns every `key.*` verb. Re-registering the group drops the added verbs unless it passes `keep_verbs=True`. Read the registry with `get_notification_group(key)`, `list_notification_groups(user=None)`, `get_notification_group_for_verb(verb)` and `is_registered_verb(verb)`, all in `baseapp_notifications.groups`.

How settings resolve: `can_user_receive_notification(user_id, verb, channel)` reads `NotificationSetting` rows whose `verb` is one of:

- for a verb outside every group: the verb's first segment (`chats.new` -> `chats`) and `_ALL_`, exactly as before groups existed;
- for a verb owned by a group: the group key and `_ALL_` only. Each group is controlled on its own: muting `chats` does not mute `chats.mentions`, and muting `comments` does not mute a `moderation` group that lists `comments.reported`. A row keyed by the verb's first segment no longer applies once the verb belongs to a group whose key is different;
- on a channel the group does not offer (see `channels`): `_ALL_` only, so a group's rows never mute channels its users cannot see.

A missing row means allowed; any inactive row for the channel or for `ALL` mutes it. `_ALL_` is the global switch and overrides every group that is not locked. `notificationSettingGroups` reports exactly this state for every verb of a group.

To catch typos, set `BASEAPP_NOTIFICATIONS_REQUIRE_REGISTERED_VERBS = True`: `send_notification` then raises `ImproperlyConfigured` for a verb no group owns. It defaults to `False`.

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| `BASEAPP_NOTIFICATIONS_EMAIL_SENDER` | `"baseapp_notifications.utils.send_notification_email"` | Dotted path to `callable(recipient, notification, **context)` that sends notification emails. A path that cannot be imported fails `manage.py check` (`baseapp_notifications.E001`/`E002`). |
| `BASEAPP_NOTIFICATIONS_REQUIRE_REGISTERED_VERBS` | `False` | Reject verbs that no registered notification group owns. |
| `BASEAPP_NOTIFICATIONS_EMAIL_REQUIRE_VERB_TEMPLATE` | `False` | Email a verb only when it has its own templates (or `email_template` is passed); no generic fallback. |

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

`actor`, `target` and `actionObject` are `Node`s. When the object's model has no `Node` type in the schema, the field is `null` instead of failing the query (over HTTP and in the subscription).

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

Set group preferences with `notificationSettingsUpdate`. It sets values (never toggles), so repeating it is safe. `channel: ALL` sets every channel the group offers (and no others). The whole input is rejected with `errors` when an entry names an unknown group (or one outside the viewer's audience), a locked group, or a channel the group does not offer. `groups` returns each changed group's resulting state.

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

`notificationSettingToggle(input: { verb, channel })` is unchanged, except that a `verb` equal to a registered group key gets the same checks: a group outside the viewer's audience or a locked group returns `errors` (field `verb`) and nothing is stored.

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
