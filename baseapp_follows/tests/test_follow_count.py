import pytest
import swapper
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from baseapp_core.models import DocumentId
from baseapp_profiles.tests.factories import ProfileFactory

Follow = swapper.load_model("baseapp_follows", "Follow")
FollowableMetadata = swapper.load_model("baseapp_follows", "FollowableMetadata")

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_follow_and_unfollow():
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()

    doc1 = DocumentId.get_or_create_for_object(profile1)
    doc2 = DocumentId.get_or_create_for_object(profile2)

    follow = Follow.objects.create(
        actor=doc1,
        target=doc2,
    )

    stats1 = FollowableMetadata.objects.get(target=doc1)
    stats2 = FollowableMetadata.objects.get(target=doc2)

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

    doc1 = DocumentId.get_or_create_for_object(profile1)
    doc2 = DocumentId.get_or_create_for_object(profile2)

    original = Follow.objects.create(
        actor=doc1,
        target=doc2,
    )

    reciprocal = Follow.objects.create(
        actor=doc2,
        target=doc1,
    )

    stats1 = FollowableMetadata.objects.get(target=doc1)
    stats2 = FollowableMetadata.objects.get(target=doc2)
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
    assert original.target_is_following_back is False  # profile2 no longer follows back profile1


def _captured_sql(ctx):
    return [q["sql"] for q in ctx.captured_queries]


def test_save_does_not_count_or_lock_followable_metadata_after_first_follow():
    """The steady-state save path must increment FollowableMetadata via an F
    expression — no COUNT(*) on follows_follow and no SELECT FOR UPDATE on
    followable_metadata. Both regress on hot targets: COUNT serializes writers
    and grows quadratically, SELECT FOR UPDATE adds an unnecessary row lock per
    follow.

    Note: the very first follow per (target / actor) does briefly SELECT FOR
    UPDATE inside update_or_create when seeding the FollowableMetadata row. That
    path fires once per pair of documents, then never again — so we bootstrap
    here and capture queries on a SECOND follow (the steady-state path).
    """
    target_profile = ProfileFactory()
    target_doc = DocumentId.get_or_create_for_object(target_profile)
    bootstrap_actor = ProfileFactory()
    bootstrap_actor_doc = DocumentId.get_or_create_for_object(bootstrap_actor)
    Follow.objects.create(actor=bootstrap_actor_doc, target=target_doc)

    new_actor = ProfileFactory()
    new_actor_doc = DocumentId.get_or_create_for_object(new_actor)
    # Pre-seed the new actor's following_count row too so its first-follow path
    # doesn't show up in the capture either — we want to lock down the steady
    # state, not the seeding sub-path.
    Follow.objects.create(
        actor=new_actor_doc,
        target=DocumentId.get_or_create_for_object(ProfileFactory()),
    )

    with CaptureQueriesContext(connection) as ctx:
        Follow.objects.create(actor=new_actor_doc, target=target_doc)

    sql = _captured_sql(ctx)
    follow_count_queries = [q for q in sql if "COUNT(*)" in q.upper() and "follows_follow" in q]
    assert follow_count_queries == [], (
        "Save path is doing a COUNT(*) on follows_follow — should be using F+1 "
        f"instead. Offending queries: {follow_count_queries}"
    )
    assert not any("FOR UPDATE" in q.upper() for q in sql), (
        "Save path is acquiring SELECT FOR UPDATE on FollowableMetadata — should "
        f"be a lock-free F-expression UPDATE. Captured queries: {sql}"
    )
    # And the F-expression update must actually have fired against
    # follows_followablemetadata.
    assert any(
        "follows_followablemetadata" in q and "followers_count" in q.lower() for q in sql
    ), f"Expected a followable_metadata UPDATE; captured: {sql}"


def test_delete_does_not_count_or_lock_followable_metadata():
    """Delete is always steady-state by definition — the FollowableMetadata row
    must exist (we incremented it on save), so the F-1 path always hits the
    UPDATE branch and never falls through to update_or_create."""
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()
    doc1 = DocumentId.get_or_create_for_object(profile1)
    doc2 = DocumentId.get_or_create_for_object(profile2)
    follow = Follow.objects.create(actor=doc1, target=doc2)

    with CaptureQueriesContext(connection) as ctx:
        follow.delete()

    sql = _captured_sql(ctx)
    follow_count_queries = [q for q in sql if "COUNT(*)" in q.upper() and "follows_follow" in q]
    assert (
        follow_count_queries == []
    ), "Delete path is doing a COUNT(*) on follows_follow — should be F-1 instead."
    assert not any("FOR UPDATE" in q.upper() for q in sql)


def test_target_is_following_back_does_not_re_enter_save():
    """The reciprocal target_is_following_back flip must use queryset .update(),
    not self.save(update_fields=...). The recursive-save pattern that was here before
    only worked because `created` was False on the second pass — fragile.
    Asserting query shape is the cleanest way to lock the new behavior in.
    """
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()
    doc1 = DocumentId.get_or_create_for_object(profile1)
    doc2 = DocumentId.get_or_create_for_object(profile2)

    Follow.objects.create(actor=doc1, target=doc2)

    with CaptureQueriesContext(connection) as ctx:
        Follow.objects.create(actor=doc2, target=doc1)  # creates the reciprocal

    sql = _captured_sql(ctx)
    # Exactly one INSERT into follows_follow — the reciprocal row. A recursive
    # `self.save()` would have re-issued an UPDATE-as-INSERT-fallback; the new
    # path uses bare UPDATEs on existing rows.
    inserts = [q for q in sql if q.lstrip().upper().startswith('INSERT INTO "FOLLOWS_FOLLOW"')]
    assert len(inserts) == 1, f"Unexpected INSERT count on follows_follow: {inserts}"


def test_recount_helpers_reconcile_drifted_metadata():
    """`recount_followers_count` / `recount_following_count` are the periodic
    reconciliation helpers — they re-derive the counter from the live row count.
    Drift the counter manually, then prove recount fixes it."""
    profile1 = ProfileFactory()
    profile2 = ProfileFactory()
    doc1 = DocumentId.get_or_create_for_object(profile1)
    doc2 = DocumentId.get_or_create_for_object(profile2)
    Follow.objects.create(actor=doc1, target=doc2)

    # Simulate drift (e.g., a bulk insert that bypassed save() / a botched migration).
    FollowableMetadata.objects.filter(target=doc2).update(followers_count=999)

    Follow.recount_followers_count(doc2)

    stats = FollowableMetadata.objects.get(target=doc2)
    assert stats.followers_count == 1

    Follow.recount_following_count(doc1)
    stats = FollowableMetadata.objects.get(target=doc1)
    assert stats.following_count == 1
