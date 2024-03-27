import pytest
import swapper
from baseapp_core.tests.factories import UserFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

Comment = swapper.load_model("baseapp_comments", "Comment")


def test_delete_user_with_comment():
    user = UserFactory()
    CommentFactory.create_batch(2, user=user)
    assert Comment.objects.filter(user=user).count() == 2
    user.delete()
    assert Comment.objects.filter(user=user).count() == 0
