from types import SimpleNamespace

import pytest
import swapper
from django.contrib.auth.models import AnonymousUser

from baseapp.content_feed.tests.factories import ContentPostFactory
from baseapp_blocks.services import (
    _BLOCKED_PROFILES_FILTERED_HINT,
    BlockLookupService,
)
from baseapp_core.tests.factories import UserFactory
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

Block = swapper.load_model("baseapp_blocks", "Block")
ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")


def _info(user) -> SimpleNamespace:
    """Minimal GraphQL info stub exposing ``info.context.user``."""
    return SimpleNamespace(context=SimpleNamespace(user=user))


def _ids(queryset) -> set[int]:
    return set(queryset.values_list("id", flat=True))


def test_anonymous_user_is_not_filtered() -> None:
    ContentPostFactory(profile=ProfileFactory())

    qs = ContentPost.objects.all()
    result = BlockLookupService().exclude_blocked_from_foreign_queryset(qs, _info(AnonymousUser()))

    # Anonymous users have no blocks: nothing is excluded, but the hint is set
    # so a later get_queryset() skips a redundant pass.
    assert result.count() == 1
    assert result._hints.get(_BLOCKED_PROFILES_FILTERED_HINT) is True


def test_excludes_blocked_and_blocker_profiles_via_current_profile() -> None:
    viewer = ProfileFactory()
    blocked = ProfileFactory()  # viewer blocks them
    blocker = ProfileFactory()  # they block viewer
    neutral = ProfileFactory()

    Block.objects.create(actor=viewer, target=blocked)
    Block.objects.create(actor=blocker, target=viewer)

    viewer_post = ContentPostFactory(profile=viewer)
    blocked_post = ContentPostFactory(profile=blocked)
    blocker_post = ContentPostFactory(profile=blocker)
    neutral_post = ContentPostFactory(profile=neutral)

    user = viewer.owner
    user.current_profile = viewer

    result = BlockLookupService().exclude_blocked_from_foreign_queryset(
        ContentPost.objects.all(), _info(user)
    )

    remaining = _ids(result)
    assert remaining == {viewer_post.id, neutral_post.id}
    assert blocked_post.id not in remaining
    assert blocker_post.id not in remaining
    assert result._hints.get(_BLOCKED_PROFILES_FILTERED_HINT) is True


def test_short_circuits_when_already_filtered() -> None:
    viewer = ProfileFactory()
    blocked = ProfileFactory()
    Block.objects.create(actor=viewer, target=blocked)
    blocked_post = ContentPostFactory(profile=blocked)

    user = viewer.owner
    user.current_profile = viewer

    qs = ContentPost.objects.all()
    qs._hints[_BLOCKED_PROFILES_FILTERED_HINT] = True

    result = BlockLookupService().exclude_blocked_from_foreign_queryset(qs, _info(user))

    # The hint is already set, so the queryset is returned untouched (no exclusion).
    assert result is qs
    assert blocked_post.id in _ids(result)


def test_fallback_uses_owned_profiles_when_no_current_profile() -> None:
    user = UserFactory()
    viewer = ProfileFactory(owner=user)
    blocked = ProfileFactory()
    blocker = ProfileFactory()
    neutral = ProfileFactory()

    Block.objects.create(actor=viewer, target=blocked)
    Block.objects.create(actor=blocker, target=viewer)

    blocked_post = ContentPostFactory(profile=blocked)
    blocker_post = ContentPostFactory(profile=blocker)
    neutral_post = ContentPostFactory(profile=neutral)

    # No current_profile on the user -> the service unions block relations across
    # all profiles the user owns.
    assert getattr(user, "current_profile", None) is None

    result = BlockLookupService().exclude_blocked_from_foreign_queryset(
        ContentPost.objects.all(), _info(user)
    )

    remaining = _ids(result)
    assert remaining == {neutral_post.id}
    assert blocked_post.id not in remaining
    assert blocker_post.id not in remaining
