import pytest
import swapper

from baseapp_core.plugins import shared_services
from baseapp_profiles.tests.factories import ProfileFactory

Block = swapper.load_model("baseapp_blocks", "Block")

pytestmark = pytest.mark.django_db


def _counts(profile):
    service = shared_services.get("blockable_metadata")
    return (
        service.get_blockers_count(profile),
        service.get_blocking_count(profile),
    )


def test_block_and_unblock():
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    block = Block.objects.create(
        actor=profile1,
        target=profile2,
    )

    p1_blockers, p1_blocking = _counts(profile1)
    p2_blockers, p2_blocking = _counts(profile2)
    assert p1_blocking == 1
    assert p2_blockers == 1

    block.delete()

    p1_blockers, p1_blocking = _counts(profile1)
    p2_blockers, p2_blocking = _counts(profile2)
    assert p1_blocking == 0
    assert p2_blockers == 0
