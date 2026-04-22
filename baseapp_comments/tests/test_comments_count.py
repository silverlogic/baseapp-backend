import pytest
import swapper

from baseapp_core.plugins import shared_services

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")
Notification = swapper.load_model("notifications", "Notification")


def test_comments_count():
    service = shared_services.get("commentable_metadata")

    target = CommentFactory()
    parent = CommentFactory(target=target)
    CommentFactory.create_batch(target=target, in_reply_to=parent, size=3)
    reply = CommentFactory(target=target, in_reply_to=parent)

    assert service.get_comments_count(parent)["total"] == 4

    CommentFactory(target=target, in_reply_to=reply)

    assert service.get_comments_count(parent)["total"] == 4

    assert service.get_comments_count(reply)["total"] == 1
