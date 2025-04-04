import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

Block = swapper.load_model("baseapp_blocks", "Block")

pytestmark = pytest.mark.django_db


def test_block_and_unblock():
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    block = Block.objects.create(
        actor=profile1,
        target=profile2,
    )

    profile1.refresh_from_db()
    profile2.refresh_from_db()

    assert profile1.blocking_count == 1
    assert profile2.blockers_count == 1

    block.delete()

    profile1.refresh_from_db()
    profile2.refresh_from_db()

    assert profile1.blocking_count == 0
    assert profile2.blockers_count == 0
