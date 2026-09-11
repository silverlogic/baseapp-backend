"""Test helpers for asserting / seeding the Mention through-table.

Replaces the `instance.mentioned_profiles.set([...])` / `.all()` / `.count()`
calls that consumer tests used while the field lived on the consuming model.
"""

from typing import TYPE_CHECKING

import swapper

from baseapp_core.models import DocumentId

if TYPE_CHECKING:
    from baseapp_mentions.models import AbstractBaseMention


def _mention_model() -> "type[AbstractBaseMention]":
    return swapper.load_model("baseapp_mentions", "Mention")


def seed_mentions(target_obj, profiles) -> None:
    """Insert Mention rows directly. Use only for setup; production code
    should call ``baseapp_mentions.services.update_mentions``."""
    Mention = _mention_model()
    doc = DocumentId.get_or_create_for_object(target_obj)
    Mention.objects.bulk_create(
        [Mention(target_document=doc, profile_id=p.pk) for p in profiles],
        ignore_conflicts=True,
    )


def mentioned_profile_ids(target_obj) -> set[int]:
    """Return the set of profile pks mentioned in ``target_obj``."""
    Mention = _mention_model()
    doc = DocumentId.get_or_create_for_object(target_obj)
    return set(Mention.objects.filter(target_document=doc).values_list("profile_id", flat=True))


def mention_count(target_obj) -> int:
    Mention = _mention_model()
    doc = DocumentId.get_or_create_for_object(target_obj)
    return Mention.objects.filter(target_document=doc).count()
