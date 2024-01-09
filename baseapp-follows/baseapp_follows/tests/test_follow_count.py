import pytest
import swapper
from baseapp_auth.tests.factories import UserFactory
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

Follow = swapper.load_model("baseapp_follows", "Follow")

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_follow_and_unfollow():
    user1 = UserFactory()
    user2 = UserFactory()

    follow = Follow.objects.create(
        actor_content_type=ContentType.objects.get_for_model(user1),
        actor_object_id=user1.id,
        target_content_type=ContentType.objects.get_for_model(user2),
        target_object_id=user2.id,
    )

    user1.refresh_from_db()
    user2.refresh_from_db()

    assert user1.following_count == 1
    assert user2.followers_count == 1

    follow.delete()

    user1.refresh_from_db()
    user2.refresh_from_db()

    assert user1.following_count == 0
    assert user2.followers_count == 0


def test_target_is_following_back():
    user1 = UserFactory()
    user2 = UserFactory()

    original = Follow.objects.create(
        actor_content_type=ContentType.objects.get_for_model(user1),
        actor_object_id=user1.id,
        target_content_type=ContentType.objects.get_for_model(user2),
        target_object_id=user2.id,
    )

    reciprocal = Follow.objects.create(
        actor_content_type=ContentType.objects.get_for_model(user2),
        actor_object_id=user2.id,
        target_content_type=ContentType.objects.get_for_model(user1),
        target_object_id=user1.id,
    )

    user1.refresh_from_db()
    user2.refresh_from_db()
    original.refresh_from_db()
    reciprocal.refresh_from_db()

    assert user1.following_count == 1
    assert user2.followers_count == 1
    assert original.target_is_following_back is True
    assert reciprocal.target_is_following_back is True

    reciprocal.delete()

    user1.refresh_from_db()
    user2.refresh_from_db()
    original.refresh_from_db()

    assert user1.following_count == 1  # user1 still follows user2
    assert user2.following_count == 0  # user2 no longer follows user1
    assert user2.followers_count == 1  # user2 still has user1 as a follower
    assert user1.followers_count == 0  # user1 has no followers anymore
    assert original.target_is_following_back is False  # user2 no longer follows back user1
