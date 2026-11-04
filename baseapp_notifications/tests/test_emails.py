from email.mime.text import MIMEText
from unittest.mock import patch

import pytest
import swapper
from django.db import transaction
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory
from baseapp_notifications.utils import resolve_notification_email_template

pytestmark = pytest.mark.django_db

Notification = swapper.load_model("notifications", "Notification")

SENT_EMAILS = []


def record_email(recipient, notification, **context) -> None:
    SENT_EMAILS.append((recipient, notification, context))


@pytest.fixture(autouse=True)
def clear_sent_emails() -> None:
    SENT_EMAILS.clear()


def email_only(**kwargs) -> dict:
    return {"verb": "event", "description": "Hello", "send_push": False, **kwargs}


# Email kwargs reach the sender only


@override_settings(
    BASEAPP_NOTIFICATIONS_EMAIL_SENDER="baseapp_notifications.tests.test_emails.record_email"
)
def test_email_kwargs_reach_only_the_sender(
    send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()
    email_context = {"invoice_owner": user}
    email_options = {"reply_to": ["support@example.com"]}

    with patch("baseapp_notifications.tasks.send_push_notification.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            send_notification(
                sender=user,
                recipient=user,
                verb="event",
                description="Hello",
                email_template="emails/custom-notification",
                email_context=email_context,
                email_options=email_options,
                url="/invoices/1",
            )

    [(_user, notification, context)] = SENT_EMAILS
    assert context["email_template"] == "emails/custom-notification"
    assert context["email_context"] is email_context
    assert context["email_options"] is email_options
    assert notification.data == {"url": "/invoices/1"}
    [push_call] = delay.call_args_list
    assert not {"email_template", "email_context", "email_options"} & set(push_call.kwargs)


def test_email_template_and_context_render_with_the_default_sender(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    sender, recipient = UserFactory.create_batch(2)

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(
            sender=sender,
            recipient=recipient,
            email_template="emails/custom-notification",
            # A model instance renders like any other context value.
            email_context={"invoice_owner": sender},
            **email_only(),
        )

    [message] = outbox
    assert message.subject == f"Invoice for {sender.email}"
    assert f"custom template txt for {sender.email}" in message.body
    assert f"custom template html for {sender.email}" in message.alternatives[0][0]


def test_email_options_with_the_default_sender(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(
            sender=user,
            recipient=user,
            email_options={
                "from_email": "billing@example.com",
                "reply_to": ["support@example.com"],
                "cc": ["cc@example.com"],
                "bcc": ["bcc@example.com"],
                "attachments": [
                    ("invoice.txt", "total: 10", "text/plain"),
                    MIMEText("second"),
                ],
                # Keys for other senders are ignored.
                "idempotency_key": "abc",
            },
            **email_only(),
        )

    [message] = outbox
    assert message.to == [user.email]
    assert message.from_email == "billing@example.com"
    assert message.reply_to == ["support@example.com"]
    assert message.cc == ["cc@example.com"]
    assert message.bcc == ["bcc@example.com"]
    assert message.attachments[0] == ("invoice.txt", "total: 10", "text/plain")
    assert len(message.attachments) == 2
    assert message.alternatives[0][1] == "text/html"


# Email after commit


def test_email_is_sent_after_commit(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks() as callbacks:
        send_notification(sender=user, recipient=user, **email_only())
        assert outbox == []
        assert Notification.objects.get().emailed is False

    for callback in callbacks:
        callback()

    assert len(outbox) == 1
    assert Notification.objects.get().emailed is True


def test_email_is_dropped_on_rollback(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError):
            with transaction.atomic():
                send_notification(sender=user, recipient=user, **email_only())
                raise RuntimeError

    assert callbacks == []
    assert outbox == []


# Template resolution


def test_dotted_verb_template_is_found_by_its_raw_name(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(sender=user, recipient=user, **email_only(verb="tests.dotted_verb"))

    [message] = outbox
    assert message.subject == "dotted verb subject"
    assert "dotted verb txt message" in message.body
    assert "dotted verb html message" in message.alternatives[0][0]


def test_legacy_slug_template_is_still_found(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(sender=user, recipient=user, **email_only(verb="Legacy Verb"))

    [message] = outbox
    assert message.subject == "legacy slug subject"
    # Parts the verb does not define fall back to the default ones.
    assert "Hello" in message.body


def test_resolve_notification_email_template() -> None:
    assert (
        resolve_notification_email_template("tests.dotted_verb")
        == "emails/notifications/tests.dotted_verb"
    )
    assert resolve_notification_email_template("Legacy Verb") == "emails/notifications/legacy-verb"
    assert resolve_notification_email_template("unknown.verb") == "emails/notification"
    assert resolve_notification_email_template("unknown.verb", "emails/x") == "emails/x"


@override_settings(BASEAPP_NOTIFICATIONS_EMAIL_REQUIRE_VERB_TEMPLATE=True)
def test_require_verb_template() -> None:
    assert resolve_notification_email_template("unknown.verb") is None
    assert (
        resolve_notification_email_template("tests.dotted_verb")
        == "emails/notifications/tests.dotted_verb"
    )
    assert resolve_notification_email_template("unknown.verb", "emails/x") == "emails/x"


@override_settings(BASEAPP_NOTIFICATIONS_EMAIL_REQUIRE_VERB_TEMPLATE=True)
def test_require_verb_template_sends_nothing_without_a_template(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(sender=user, recipient=user, **email_only(verb="unknown.verb"))
        send_notification(
            sender=user,
            recipient=user,
            email_template="emails/custom-notification",
            email_context={"invoice_owner": user},
            **email_only(verb="unknown.other"),
        )

    assert [message.subject for message in outbox] == [f"Invoice for {user.email}"]
    assert dict(Notification.objects.values_list("verb", "emailed")) == {
        "unknown.verb": False,
        "unknown.other": True,
    }


def test_each_part_falls_back_through_raw_then_slug_then_generic(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    # The raw name defines only the subject and the legacy slug name only the text body.
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(sender=user, recipient=user, **email_only(verb="tests.mixed"))

    [message] = outbox
    assert message.subject == "mixed raw subject"
    assert "mixed slug txt message" in message.body
    assert "Hello" in message.alternatives[0][0]


# Validation and failures


def test_single_address_email_options_are_listed(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(
            sender=user,
            recipient=user,
            email_options={"reply_to": "support@example.com", "cc": "cc@example.com"},
            **email_only(),
        )

    [message] = outbox
    assert message.reply_to == ["support@example.com"]
    assert message.cc == ["cc@example.com"]


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"email_options": {"bcc": {"bcc@example.com"}}}, TypeError),
        ({"email_options": ["reply_to"]}, TypeError),
        ({"email_context": ["value"]}, TypeError),
        ({"email_context": {"recipient": "someone else"}}, ValueError),
        ({"email_context": {"verb": "other"}}, ValueError),
    ],
)
def test_invalid_email_arguments_raise_when_sending(
    send_notification, django_capture_on_commit_callbacks, kwargs, error
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks() as callbacks:
        with pytest.raises(error):
            send_notification(sender=user, recipient=user, **kwargs, **email_only())

    assert callbacks == []
    assert not Notification.objects.exists()


def test_email_context_overrides_other_render_keys(
    outbox, send_notification, django_capture_on_commit_callbacks
) -> None:
    user = UserFactory()

    with django_capture_on_commit_callbacks(execute=True):
        send_notification(
            sender=user,
            recipient=user,
            email_context={"email_message": "Overridden"},
            **email_only(),
        )

    [message] = outbox
    assert "Overridden" in message.body


FAILED_RECIPIENTS = []


def fail_for_first_recipient(recipient, notification, **context) -> None:
    if not FAILED_RECIPIENTS:
        FAILED_RECIPIENTS.append(recipient)
        raise RuntimeError("SMTP down")
    SENT_EMAILS.append((recipient, notification, context))


@override_settings(
    BASEAPP_NOTIFICATIONS_EMAIL_SENDER=(
        "baseapp_notifications.tests.test_emails.fail_for_first_recipient"
    )
)
def test_failing_sender_after_commit_does_not_drop_other_callbacks(
    send_notification, django_capture_on_commit_callbacks, caplog
) -> None:
    FAILED_RECIPIENTS.clear()
    users = UserFactory.create_batch(3)
    other_app_calls = []

    with patch("baseapp_notifications.tasks.send_push_notification.delay") as delay:
        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                send_notification(sender=users[0], recipient=users, verb="event", description="Hi")
                transaction.on_commit(lambda: other_app_calls.append(True))

    assert FAILED_RECIPIENTS == [users[0]]
    assert [recipient for recipient, _notification, _context in SENT_EMAILS] == users[1:]
    assert sorted(call.args[0] for call in delay.call_args_list) == sorted(u.id for u in users)
    assert other_app_calls == [True]
    assert dict(Notification.objects.values_list("recipient_id", "emailed")) == {
        users[0].id: False,
        users[1].id: True,
        users[2].id: True,
    }
    assert "Sending the 'event' notification email to user" in caplog.text


@override_settings(
    BASEAPP_NOTIFICATIONS_EMAIL_SENDER=(
        "baseapp_notifications.tests.test_emails.fail_for_first_recipient"
    )
)
@pytest.mark.django_db(transaction=True)
def test_failing_sender_outside_a_transaction_raises(send_notification) -> None:
    FAILED_RECIPIENTS.clear()
    user = UserFactory()

    with pytest.raises(RuntimeError, match="SMTP down"):
        send_notification(sender=user, recipient=user, **email_only())
