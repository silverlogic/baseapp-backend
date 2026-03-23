import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_follows.models import FollowStats, get_document_id_for_object
from baseapp_profiles.tests.factories import ProfileFactory

Follow = swapper.load_model("baseapp_follows", "Follow")

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_follow_and_unfollow():
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    doc1 = get_document_id_for_object(profile1)
    doc2 = get_document_id_for_object(profile2)

    follow = Follow.objects.create(
        actor=doc1,
        target=doc2,
    )

    stats1 = FollowStats.objects.get(target=doc1)
    stats2 = FollowStats.objects.get(target=doc2)

    assert stats1.following_count == 1
    assert stats2.followers_count == 1

    follow.delete()

    stats1.refresh_from_db()
    stats2.refresh_from_db()

    assert stats1.following_count == 0
    assert stats2.followers_count == 0


def test_target_is_following_back():
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    doc1 = get_document_id_for_object(profile1)
    doc2 = get_document_id_for_object(profile2)

    original = Follow.objects.create(
        actor=doc1,
        target=doc2,
    )

    reciprocal = Follow.objects.create(
        actor=doc2,
        target=doc1,
    )

    stats1 = FollowStats.objects.get(target=doc1)
    stats2 = FollowStats.objects.get(target=doc2)
    original.refresh_from_db()
    reciprocal.refresh_from_db()

    assert stats1.following_count == 1
    assert stats2.followers_count == 1
    assert original.target_is_following_back is True
    assert reciprocal.target_is_following_back is True

    reciprocal.delete()

    stats1.refresh_from_db()
    stats2.refresh_from_db()
    original.refresh_from_db()

    assert stats1.following_count == 1  # profile1 still follows profile2
    assert stats2.following_count == 0  # profile2 no longer follows profile1
    assert stats2.followers_count == 1  # profile2 still has profile1 as a follower
    assert stats1.followers_count == 0  # profile1 has no followers anymore
    assert (
        original.target_is_following_back is False
    )  # profile2 no longer follows back profile1
