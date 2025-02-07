from unittest.mock import patch

import pytest
import swapper
from django.test import override_settings

from baseapp_core.tests.factories import UserFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")
Notification = swapper.load_model("notifications", "Notification")


def test_user_receieve_notification_when_comment_is_created():
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


def test_user_receieve_notification_when_reply_is_created():
    user = UserFactory()
    friend = UserFactory()

    target = CommentFactory()
    parent = CommentFactory(target=target, user=user)

    with override_settings(BASEAPP_COMMENTS_ENABLE_NOTIFICATIONS=True):
        with patch("baseapp_comments.notifications.send_reply_created_notification.delay") as mock:
            comment = CommentFactory(target=target, user=friend, in_reply_to=parent)
            assert mock.called
            assert mock.call_args.args == (comment.pk,)
