import pytest
import swapper
from baseapp_auth.tests.factories import UserFactory
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

Block = swapper.load_model("baseapp_blocks", "Block")

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_block_and_unblock():
    user1 = UserFactory()
    user2 = UserFactory()

    block = Block.objects.create(
        actor_content_type=ContentType.objects.get_for_model(user1),
        actor_object_id=user1.id,
        target_content_type=ContentType.objects.get_for_model(user2),
        target_object_id=user2.id,
    )

    user1.refresh_from_db()
    user2.refresh_from_db()

    assert user1.blocking_count == 1
    assert user2.blockers_count == 1

    block.delete()

    user1.refresh_from_db()
    user2.refresh_from_db()

    assert user1.blocking_count == 0
    assert user2.blockers_count == 0
