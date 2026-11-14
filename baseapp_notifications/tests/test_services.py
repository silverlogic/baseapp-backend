from unittest.mock import patch

import pytest
import swapper
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory
from baseapp_notifications.groups import register_notification_group

from .factories import NotificationSettingFactory

pytestmark = pytest.mark.django_db

Notification = swapper.load_model("notifications", "Notification")
NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
Channels = NotificationSetting.NotificationChannelTypes

SENT_EMAILS = []


def record_email(recipient, notification, **context) -> None:
    SENT_EMAILS.append((recipient, notification, context))


def skip_email(recipient, notification, **context) -> bool:
    return False


@pytest.fixture(autouse=True)
def clear_sent_emails() -> None:
    SENT_EMAILS.clear()


def in_app_only(**kwargs) -> dict:
    return {"verb": "event", "send_email": False, "send_push": False, **kwargs}


# Recipients


def test_single_recipient_returns_notify_results(send_notification) -> None:
    user = UserFactory()

    result = send_notification(sender=user, recipient=user, **in_app_only())

    [(_receiver, [notification])] = result
    assert notification.recipient == user


def test_list_of_recipients_honours_each_users_settings(send_notification) -> None:
    sender, first, muted, second = UserFactory.create_batch(4)
    NotificationSettingFactory(user=muted, verb="event", channel=Channels.IN_APP, is_active=False)

    result = send_notification(
        sender=sender, recipient=[first, muted, None, second], **in_app_only()
    )

    assert len(result) == 2
    assert set(Notification.objects.values_list("recipient", flat=True)) == {first.pk, second.pk}


def test_queryset_and_group_recipients(send_notification) -> None:
    sender = UserFactory()
    users = UserFactory.create_batch(2)
    group = Group.objects.create(name="team")
    group.user_set.add(*users)

    send_notification(
        sender=sender, recipient=type(sender).objects.filter(pk=users[0].pk), **in_app_only()
    )
    send_notification(sender=sender, recipient=group, **in_app_only())

    assert Notification.objects.filter(recipient=users[0]).count() == 2
    assert Notification.objects.filter(recipient=users[1]).count() == 1


def test_each_recipient_gets_its_own_email(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    sender = UserFactory()
    users = UserFactory.create_batch(2)

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(
            sender=sender, recipient=users, verb="event", description="Hello", send_push=False
        )

    assert sorted(message.to[0] for message in outbox) == sorted(user.email for user in users)
    assert Notification.objects.filter(emailed=True).count() == 2


# Push


def test_push_is_queued_after_commit(send_notification, django_capture_on_commit_callbacks) -> None:
    user = UserFactory()

    with patch("baseapp_notifications.tasks.send_push_notification.delay") as delay:
        with django_capture_on_commit_callbacks() as callbacks:
            send_notification(
                sender=user,
                recipient=user,
                verb="event",
                description="Body",
                add_to_history=False,
                send_email=False,
            )
            assert not delay.called

        assert len(callbacks) == 1
        callbacks[0]()

    delay.assert_called_once_with(user.id, push_title=None, push_description="Body")


def test_push_is_dropped_on_rollback(send_notification, django_capture_on_commit_callbacks) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks() as callbacks:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                send_notification(
                    sender=user,
                    recipient=user,
                    verb="event",
                    description="Body",
                    add_to_history=False,
                    send_email=False,
                )
                raise RuntimeError

    assert callbacks == []


# Email sender hook


@override_settings(
    BASEAPP_NOTIFICATIONS_EMAIL_SENDER="baseapp_notifications.tests.test_services.record_email"
)
def test_custom_email_sender_receives_recipient_notification_and_context(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    sender, recipient = UserFactory.create_batch(2)

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(
            sender=sender,
            recipient=recipient,
            verb="event",
            description="Hello",
            send_push=False,
            url="/somewhere",
        )

    assert outbox == []
    [(user, notification, context)] = SENT_EMAILS
    assert user == recipient
    assert notification == Notification.objects.get()
    assert notification.emailed is True
    assert context["sender"] == sender
    assert context["verb"] == "event"
    assert context["email_subject"] == "Hello"
    assert context["url"] == "/somewhere"
    assert context["email_template"] is None
    assert context["email_context"] is None
    assert context["email_options"] is None


@override_settings(
    BASEAPP_NOTIFICATIONS_EMAIL_SENDER="baseapp_notifications.tests.test_services.skip_email"
)
def test_email_sender_returning_false_leaves_notification_not_emailed(
    send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(sender=user, recipient=user, verb="event", send_push=False)

    assert Notification.objects.get().emailed is False


# Registered verbs


def test_unregistered_verbs_are_allowed_by_default(
    notification_groups_registry, send_notification
) -> None:
    user = UserFactory()
    send_notification(sender=user, recipient=user, **in_app_only(verb="anything"))
    assert Notification.objects.count() == 1


@override_settings(BASEAPP_NOTIFICATIONS_REQUIRE_REGISTERED_VERBS=True)
def test_require_registered_verbs(notification_groups_registry, send_notification) -> None:
    register_notification_group("comments", label="Comments")
    user = UserFactory()

    with pytest.raises(ImproperlyConfigured):
        send_notification(sender=user, recipient=user, **in_app_only(verb="anything"))

    send_notification(sender=user, recipient=user, **in_app_only(verb="comments.reply"))
    assert list(Notification.objects.values_list("verb", flat=True)) == ["comments.reply"]


def test_locked_group_ignores_settings_when_sending(
    notification_groups_registry, send_notification
) -> None:
    register_notification_group("security", label="Security", is_locked=True)
    user = UserFactory()
    NotificationSettingFactory(user=user, verb="security", channel=Channels.ALL, is_active=False)

    send_notification(sender=user, recipient=user, **in_app_only(verb="security.new_login"))

    assert Notification.objects.count() == 1
