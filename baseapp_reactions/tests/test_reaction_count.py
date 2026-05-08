import pytest
import swapper

from baseapp_comments.tests.factories import CommentFactory

from .factories import ReactionFactory

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
ReactableMetadata = swapper.load_model("baseapp_reactions", "ReactableMetadata")
ReactionTypes = Reaction.ReactionTypes

pytestmark = pytest.mark.django_db


def test_reaction_save_creates_metadata_and_increments_count():
    """Creating a Reaction through the ORM should populate `ReactableMetadata`
    for the target with a fresh per-type count dict (LIKE bucket + total)."""
    target = CommentFactory()

    ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)

    metadata = ReactableMetadata.get_for_object(target)
    assert metadata is not None
    assert metadata.reactions_count["total"] == 1
    assert metadata.reactions_count["LIKE"] == 1
    assert metadata.reactions_count["DISLIKE"] == 0


def test_reaction_save_aggregates_multiple_reactions_per_type():
    """Multiple reactions of the same type should accumulate in that bucket and total."""
    target = CommentFactory()

    ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)
    ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)
    ReactionFactory(target=target, reaction_type=ReactionTypes.DISLIKE)

    metadata = ReactableMetadata.get_for_object(target)
    assert metadata.reactions_count["total"] == 3
    assert metadata.reactions_count["LIKE"] == 2
    assert metadata.reactions_count["DISLIKE"] == 1


def test_reaction_delete_decrements_count():
    target = CommentFactory()
    ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)
    second = ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)

    metadata = ReactableMetadata.get_for_object(target)
    assert metadata.reactions_count["total"] == 2

    second.delete()

    metadata.refresh_from_db()
    assert metadata.reactions_count["total"] == 1
    assert metadata.reactions_count["LIKE"] == 1


def test_reaction_delete_resets_to_zero_when_no_reactions_left():
    target = CommentFactory()
    reaction = ReactionFactory(target=target, reaction_type=ReactionTypes.DISLIKE)

    metadata = ReactableMetadata.get_for_object(target)
    assert metadata.reactions_count["total"] == 1

    reaction.delete()

    metadata.refresh_from_db()
    assert metadata.reactions_count["total"] == 0
    assert metadata.reactions_count["LIKE"] == 0
    assert metadata.reactions_count["DISLIKE"] == 0


def test_reactions_count_isolated_per_target():
    """Reactions against target A must not bleed into target B's metadata."""
    target_a = CommentFactory()
    target_b = CommentFactory()

    ReactionFactory(target=target_a, reaction_type=ReactionTypes.LIKE)

    metadata_a = ReactableMetadata.get_for_object(target_a)
    metadata_b = ReactableMetadata.get_for_object(target_b)

    assert metadata_a.reactions_count["total"] == 1
    assert metadata_b is None or metadata_b.reactions_count["total"] == 0


def test_update_reactions_count_recomputes_from_existing_rows():
    """`Reaction.update_reactions_count(target)` should recompute the per-type
    counts from the live `Reaction` rows even if the metadata row is stale."""
    target = CommentFactory()

    ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)
    ReactionFactory(target=target, reaction_type=ReactionTypes.DISLIKE)

    metadata = ReactableMetadata.get_for_object(target)
    metadata.reactions_count = {"total": 0, "LIKE": 0, "DISLIKE": 0}
    metadata.save(update_fields=["reactions_count"])

    Reaction.update_reactions_count(target)

    metadata.refresh_from_db()
    assert metadata.reactions_count["total"] == 2
    assert metadata.reactions_count["LIKE"] == 1
    assert metadata.reactions_count["DISLIKE"] == 1


def test_update_reactions_count_no_op_when_target_is_none():
    """`update_reactions_count(None)` should silently no-op rather than crash."""
    Reaction.update_reactions_count(None)  # should not raise
