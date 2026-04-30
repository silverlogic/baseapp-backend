"""Test helpers for asserting / seeding the Mention through-table.

Replaces the `instance.mentioned_profiles.set([...])` / `.all()` / `.count()`
calls that consumer tests used while the field lived on the consuming model.
"""

import swapper

from baseapp_core.models import DocumentId


def _mention_model():
    return swapper.load_model("baseapp_mentions", "Mention")


def seed_mentions(target_obj, profiles):
    """Insert Mention rows directly. Use only for setup; production code
    should call ``baseapp_mentions.services.update_mentions``."""
    Mention = _mention_model()
    doc = DocumentId.get_or_create_for_object(target_obj)
    Mention.objects.bulk_create(
        [Mention(target=doc, profile_id=p.pk) for p in profiles],
        ignore_conflicts=True,
    )


def mentioned_profile_ids(target_obj):
    """Return the set of profile pks mentioned in ``target_obj``."""
    Mention = _mention_model()
    doc = DocumentId.get_or_create_for_object(target_obj)
    return set(Mention.objects.filter(target=doc).values_list("profile_id", flat=True))


def mention_count(target_obj):
    Mention = _mention_model()
    doc = DocumentId.get_or_create_for_object(target_obj)
    return Mention.objects.filter(target=doc).count()
