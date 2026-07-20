from unittest.mock import patch

import pytest
import swapper
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")
Notification = swapper.load_model("notifications", "Notification")


def test_user_receieve_notification_when_comment_is_created() -> None:
    user = UserFactory()
    friend = UserFactory()

    target = CommentFactory(user=user)

    with override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True):
        with patch(
            "baseapp_comments.notifications.send_comment_created_notification.delay"
        ) as mock:
            comment = CommentFactory(target=target, user=friend)
            assert mock.called
            assert mock.call_args.args == (comment.pk, user.id)


def test_user_receieve_notification_when_reply_is_created() -> None:
    user = UserFactory()
    friend = UserFactory()

    target = CommentFactory()
    parent = CommentFactory(target=target, user=user)

    with override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True):
        with patch("baseapp_comments.notifications.send_reply_created_notification.delay") as mock:
            comment = CommentFactory(target=target, user=friend, in_reply_to=parent)
            assert mock.called
            assert mock.call_args.args == (comment.pk,)


def test_comment_created_notification_sends_email_by_default(outbox) -> None:
    user = UserFactory()
    friend = UserFactory()
    target = CommentFactory(user=user)

    with override_settings(
        BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True,
        BASEAPP_COMMENTS_NOTIFICATION_CREATED_EMAIL=True,
    ):
        CommentFactory(target=target, user=friend)

    assert len(outbox) == 1
    assert outbox[0].to == [user.email]
    assert Notification.objects.filter(recipient=user, verb="COMMENTS.COMMENT_CREATED").exists()


def test_comment_created_notification_skips_email_when_disabled(outbox) -> None:
    user = UserFactory()
    friend = UserFactory()
    target = CommentFactory(user=user)

    with override_settings(
        BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True,
        BASEAPP_COMMENTS_NOTIFICATION_CREATED_EMAIL=False,
    ):
        CommentFactory(target=target, user=friend)

    assert len(outbox) == 0
    # The in-app notification is unaffected — only the email is suppressed.
    assert Notification.objects.filter(recipient=user, verb="COMMENTS.COMMENT_CREATED").exists()


def test_reply_created_notification_sends_email_by_default(outbox) -> None:
    user = UserFactory()
    friend = UserFactory()
    # Suppress notifications while building the parent, which would otherwise email its target's owner.
    with override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=False):
        target = CommentFactory()
        parent = CommentFactory(target=target, user=user)

    with override_settings(
        BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True,
        BASEAPP_COMMENTS_NOTIFICATION_REPLY_EMAIL=True,
    ):
        CommentFactory(target=target, user=friend, in_reply_to=parent)

    assert len(outbox) == 1
    assert outbox[0].to == [user.email]
    assert Notification.objects.filter(
        recipient=user, verb="COMMENTS.COMMENT_REPLY_CREATED"
    ).exists()


def test_reply_created_notification_skips_email_when_disabled(outbox) -> None:
    user = UserFactory()
    friend = UserFactory()
    # Suppress notifications while building the parent, which would otherwise email its target's owner.
    with override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=False):
        target = CommentFactory()
        parent = CommentFactory(target=target, user=user)

    with override_settings(
        BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True,
        BASEAPP_COMMENTS_NOTIFICATION_REPLY_EMAIL=False,
    ):
        CommentFactory(target=target, user=friend, in_reply_to=parent)

    assert len(outbox) == 0
    # The in-app notification is unaffected — only the email is suppressed.
    assert Notification.objects.filter(
        recipient=user, verb="COMMENTS.COMMENT_REPLY_CREATED"
    ).exists()
