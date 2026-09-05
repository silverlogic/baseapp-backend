import pytest
import swapper
from django.contrib.auth import get_user_model

from baseapp_core.models import DocumentId
from baseapp_follows.models import FollowStats
from baseapp_profiles.tests.factories import ProfileFactory

Follow = swapper.load_model("baseapp_follows", "Follow")
User = get_user_model()

pytestmark = pytest.mark.django_db


def test_deleting_follower_user_cascades():
    """Deleting a user who follows someone should not raise IntegrityError."""
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    doc1 = DocumentId.get_or_create_for_object(profile1)
    doc2 = DocumentId.get_or_create_for_object(profile2)

    Follow.objects.create(actor=doc1, target=doc2)

    assert FollowStats.objects.filter(target=doc1).exists()
    assert FollowStats.objects.filter(target=doc2).exists()
    assert Follow.objects.count() == 1

    # Delete the follower's user — triggers pgtrigger DELETE on DocumentId
    profile1.owner.delete()

    assert Follow.objects.count() == 0
    assert not FollowStats.objects.filter(target_id=doc1.pk).exists()


def test_deleting_followed_user_cascades():
    """Deleting a user who is being followed should not raise IntegrityError."""
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    doc1 = DocumentId.get_or_create_for_object(profile1)
    doc2 = DocumentId.get_or_create_for_object(profile2)

    Follow.objects.create(actor=doc1, target=doc2)

    # Delete the followed user
    profile2.owner.delete()

    assert Follow.objects.count() == 0
    assert not FollowStats.objects.filter(target_id=doc2.pk).exists()
