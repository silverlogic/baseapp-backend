"""Tests for `update_mentions` — the single public seam consumer mutations
(comments / content_feed / chats) call when persisting `mentionedProfileIds`.

The semantics that must hold:

- An empty set of resolved profiles clears the existing mentions.
- A new set replaces the existing rows (delta-based: only changed rows get
  inserted / deleted).
- `exclude_profile` filters out self-mentions.
- Calling twice with the same set is idempotent — no signal fires the second
  time.
- The `mentions_changed` signal fires once per call with `added` / `removed`
  profile pks describing the delta.
"""

from collections.abc import Generator

import pytest
import swapper

from baseapp_comments.tests.factories import CommentFactory
from baseapp_mentions.services import MentionsService
from baseapp_mentions.signals import mentions_changed
from baseapp_mentions.tests.helpers import mentioned_profile_ids, seed_mentions
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

Mention = swapper.load_model("baseapp_mentions", "Mention")


class _SignalCapture:
    """Collect every fire of `mentions_changed` for assertion."""

    def __init__(self) -> None:
        self.events = []

    def __call__(self, sender, target, added, removed, **kwargs) -> None:
        self.events.append({"target": target, "added": list(added), "removed": list(removed)})


@pytest.fixture
def captured_signal() -> Generator[_SignalCapture, None, None]:
    capture = _SignalCapture()
    mentions_changed.connect(capture, weak=False)
    yield capture
    mentions_changed.disconnect(capture)


def test_inserts_mentions_for_new_profiles(
    captured_signal, django_capture_on_commit_callbacks
) -> None:
    target = CommentFactory()
    a = ProfileFactory()
    b = ProfileFactory()

    with django_capture_on_commit_callbacks(execute=True):
        MentionsService().update_mentions(target, [a.relay_id, b.relay_id])

    assert mentioned_profile_ids(target) == {a.pk, b.pk}
    assert len(captured_signal.events) == 1
    assert set(captured_signal.events[0]["added"]) == {a.pk, b.pk}
    assert captured_signal.events[0]["removed"] == []


def test_replaces_existing_mentions_with_delta(
    captured_signal, django_capture_on_commit_callbacks
) -> None:
    target = CommentFactory()
    a = ProfileFactory()
    b = ProfileFactory()
    c = ProfileFactory()
    seed_mentions(target, [a, b])
    captured_signal.events.clear()  # ignore pre-update state

    with django_capture_on_commit_callbacks(execute=True):
        MentionsService().update_mentions(target, [b.relay_id, c.relay_id])

    assert mentioned_profile_ids(target) == {b.pk, c.pk}
    assert len(captured_signal.events) == 1
    event = captured_signal.events[0]
    assert event["added"] == [c.pk]
    assert event["removed"] == [a.pk]


def test_empty_list_clears_all_mentions(
    captured_signal, django_capture_on_commit_callbacks
) -> None:
    target = CommentFactory()
    a = ProfileFactory()
    seed_mentions(target, [a])
    captured_signal.events.clear()

    with django_capture_on_commit_callbacks(execute=True):
        MentionsService().update_mentions(target, [])

    assert mentioned_profile_ids(target) == set()
    assert len(captured_signal.events) == 1
    assert captured_signal.events[0]["removed"] == [a.pk]


def test_exclude_profile_filters_self_mention(captured_signal) -> None:
    target = CommentFactory()
    me = ProfileFactory()
    friend = ProfileFactory()

    MentionsService().update_mentions(target, [me.relay_id, friend.relay_id], exclude_profile=me)

    assert mentioned_profile_ids(target) == {friend.pk}


def test_idempotent_call_does_not_fire_signal(
    captured_signal, django_capture_on_commit_callbacks
) -> None:
    target = CommentFactory()
    a = ProfileFactory()
    with django_capture_on_commit_callbacks(execute=True):
        MentionsService().update_mentions(target, [a.relay_id])
    captured_signal.events.clear()

    with django_capture_on_commit_callbacks(execute=True):
        MentionsService().update_mentions(target, [a.relay_id])

    assert mentioned_profile_ids(target) == {a.pk}
    assert captured_signal.events == []


def test_malformed_relay_ids_are_dropped(captured_signal) -> None:
    target = CommentFactory()
    real = ProfileFactory()

    MentionsService().update_mentions(target, [real.relay_id, "not-a-real-id", ""])

    assert mentioned_profile_ids(target) == {real.pk}
