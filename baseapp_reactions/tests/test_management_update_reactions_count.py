from io import StringIO
from unittest.mock import patch

import pytest
import swapper
from django.core.management import call_command

from baseapp_comments.tests.factories import CommentFactory

from .factories import ReactionFactory

Reaction = swapper.load_model("baseapp_reactions", "Reaction")
ReactableMetadata = swapper.load_model("baseapp_reactions", "ReactableMetadata")
ReactionTypes = Reaction.ReactionTypes

pytestmark = pytest.mark.django_db


def _call() -> str:
    out = StringIO()
    call_command("update_reactions_count", stdout=out)
    return out.getvalue()


def test_command_recomputes_metadata_from_existing_reactions() -> None:
    """Even with stale metadata rows, the command should produce per-type counts
    that match the live `Reaction` rows."""
    target = CommentFactory()

    ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)
    ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)
    ReactionFactory(target=target, reaction_type=ReactionTypes.DISLIKE)

    metadata = ReactableMetadata.get_for_object(target)
    metadata.reactions_count = {"total": 0, "LIKE": 0, "DISLIKE": 0}
    metadata.save(update_fields=["reactions_count"])

    output = _call()

    metadata.refresh_from_db()
    assert metadata.reactions_count == {"total": 3, "LIKE": 2, "DISLIKE": 1}
    assert "Recomputed reactions_count for 1 target(s)" in output


def test_command_iterates_over_distinct_targets_only() -> None:
    """A target with multiple reactions should only be recomputed once."""
    target_a = CommentFactory()
    target_b = CommentFactory()

    ReactionFactory(target=target_a, reaction_type=ReactionTypes.LIKE)
    ReactionFactory(target=target_a, reaction_type=ReactionTypes.LIKE)
    ReactionFactory(target=target_b, reaction_type=ReactionTypes.DISLIKE)

    with patch.object(
        Reaction, "update_reactions_count", wraps=Reaction.update_reactions_count
    ) as wrapped:
        _call()

    targets_recomputed = [call.args[0].pk for call in wrapped.call_args_list]
    assert sorted(targets_recomputed) == sorted([target_a.pk, target_b.pk])


def test_command_skips_targets_when_content_object_is_missing() -> None:
    """If `DocumentId.content_object` resolves to None (orphaned content type),
    the command should skip without crashing."""
    target = CommentFactory()
    ReactionFactory(target=target, reaction_type=ReactionTypes.LIKE)

    from baseapp_core.models import DocumentId

    with patch.object(DocumentId, "content_object", None):
        output = _call()

    assert "skipped 1" in output


def test_command_no_op_when_no_reactions() -> None:
    output = _call()
    assert "Recomputed reactions_count for 0 target(s)" in output
