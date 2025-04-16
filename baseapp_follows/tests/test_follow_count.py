import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_profiles.tests.factories import ProfileFactory

Follow = swapper.load_model("baseapp_follows", "Follow")

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_follow_and_unfollow():
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    follow = Follow.objects.create(
        actor=profile1,
        target=profile2,
    )

    profile1.refresh_from_db()
    profile2.refresh_from_db()

    assert profile1.following_count == 1
    assert profile2.followers_count == 1

    follow.delete()

    profile1.refresh_from_db()
    profile2.refresh_from_db()

    assert profile1.following_count == 0
    assert profile2.followers_count == 0


def test_target_is_following_back():
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    original = Follow.objects.create(
        actor=profile1,
        target=profile2,
    )

    reciprocal = Follow.objects.create(
        actor=profile2,
        target=profile1,
    )

    profile1.refresh_from_db()
    profile2.refresh_from_db()
    original.refresh_from_db()
    reciprocal.refresh_from_db()

    assert profile1.following_count == 1
    assert profile2.followers_count == 1
    assert original.target_is_following_back is True
    assert reciprocal.target_is_following_back is True

    reciprocal.delete()

    profile1.refresh_from_db()
    profile2.refresh_from_db()
    original.refresh_from_db()

    assert profile1.following_count == 1  # profile1 still follows profile2
    assert profile2.following_count == 0  # profile2 no longer follows profile1
    assert profile2.followers_count == 1  # profile2 still has profile1 as a follower
    assert profile1.followers_count == 0  # profile1 has no followers anymore
    assert original.target_is_following_back is False  # profile2 no longer follows back profile1
