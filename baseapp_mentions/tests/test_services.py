"""Resolver tests for `resolve_mentioned_profiles`.

The resolver is the seam every consumer (comments, chats, content_feed) routes
through; bugs here surface as missed notifications or dropped tags. The cases
below cover the contract the upstream mutations rely on:

- valid Relay IDs map to Profile instances
- `exclude_profile` removes a self-mention regardless of input order
- malformed Relay IDs are dropped silently (a flaky client must not break the
  parent mutation)
- IDs pointing at non-existent rows are dropped
- empty / `None` inputs return `[]`
"""

import pytest
import swapper

from baseapp_mentions.services import resolve_mentioned_profiles
from baseapp_profiles.tests.factories import ProfileFactory

pytestmark = pytest.mark.django_db

Profile = swapper.load_model("baseapp_profiles", "Profile")


def test_resolves_valid_relay_ids_to_profiles():
    a = ProfileFactory()
    b = ProfileFactory()

    profiles = resolve_mentioned_profiles([a.relay_id, b.relay_id])

    assert {p.pk for p in profiles} == {a.pk, b.pk}


def test_returns_empty_list_for_empty_iterable():
    assert resolve_mentioned_profiles([]) == []


def test_returns_empty_list_for_none():
    assert resolve_mentioned_profiles(None) == []


def test_drops_malformed_relay_ids():
    valid = ProfileFactory()
    profiles = resolve_mentioned_profiles(["not-a-relay-id", valid.relay_id, "!!!", ""])

    assert [p.pk for p in profiles] == [valid.pk]


def test_drops_relay_ids_pointing_at_non_existent_profiles():
    valid = ProfileFactory()
    stale = ProfileFactory()
    stale_relay_id = stale.relay_id
    stale.delete()

    profiles = resolve_mentioned_profiles([valid.relay_id, stale_relay_id])

    assert [p.pk for p in profiles] == [valid.pk]


def test_excludes_self_when_exclude_profile_provided():
    me = ProfileFactory()
    friend = ProfileFactory()

    profiles = resolve_mentioned_profiles(
        [me.relay_id, friend.relay_id],
        exclude_profile=me,
    )

    assert [p.pk for p in profiles] == [friend.pk]


def test_exclude_profile_with_unsaved_instance_is_a_noop():
    """A profile without a pk can't match anything in the queryset; the
    resolver must not blow up trying to exclude it."""
    a = ProfileFactory()
    b = ProfileFactory()
    unsaved = Profile()

    profiles = resolve_mentioned_profiles(
        [a.relay_id, b.relay_id],
        exclude_profile=unsaved,
    )

    assert {p.pk for p in profiles} == {a.pk, b.pk}


def test_duplicate_relay_ids_collapse_to_unique_profiles():
    a = ProfileFactory()

    profiles = resolve_mentioned_profiles([a.relay_id, a.relay_id])

    assert [p.pk for p in profiles] == [a.pk]
