import pytest
import swapper

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")
Notification = swapper.load_model("notifications", "Notification")


def test_comments_count():
    target = CommentFactory()
    parent = CommentFactory(target=target)
    CommentFactory.create_batch(target=target, in_reply_to=parent, size=3)
    reply = CommentFactory(target=target, in_reply_to=parent)

    parent.refresh_from_db()
    assert parent.comments_count["total"] == 4

    CommentFactory(target=target, in_reply_to=reply)

    parent.refresh_from_db()
    assert parent.comments_count["total"] == 4

    reply.refresh_from_db()
    assert reply.comments_count["total"] == 1
