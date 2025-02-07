import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_core.tests.factories import UserFactory

from .factories import CommentFactory

pytestmark = pytest.mark.django_db

User = get_user_model()
Comment = swapper.load_model("baseapp_comments", "Comment")


def test_delete_user_with_comment():
    user = UserFactory()
    user_id = user.pk
    CommentFactory.create_batch(2, user=user)
    assert Comment.objects_visible.filter(user_id=user_id).count() == 2
    user.delete()
    assert Comment.objects_visible.filter(user_id=user_id).count() == 0
    assert User.objects.all().count() == 0
