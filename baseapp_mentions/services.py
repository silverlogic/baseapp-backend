from typing import Iterable, List, Optional

import swapper
from django.db import transaction

from baseapp_core.graphql.utils import get_pk_from_relay_id
from baseapp_core.models import DocumentId

from .signals import mentions_changed

Profile = swapper.load_model("baseapp_profiles", "Profile")


def resolve_mentioned_profiles(
    mentioned_profile_ids: Iterable[str],
    exclude_profile: Optional["Profile"] = None,
) -> List["Profile"]:
    """Resolve Relay global IDs to Profile instances, filtering out self-mention.

    Silently drops malformed or stale IDs so a flaky client reference does not
    break the parent mutation.
    """
    pks: List[int] = []
    for relay_id in mentioned_profile_ids or []:
        try:
            pk = get_pk_from_relay_id(relay_id)
        except Exception:  # noqa: BLE001 — malformed IDs are dropped intentionally
            continue
        if pk is None:
            continue
        # `get_pk_from_relay_id` returns whatever survived hashids/base64 decoding —
        # for some malformed inputs that's an empty string or a non-numeric chunk
        # rather than a raised exception. Coerce to int explicitly so a stray value
        # never reaches the queryset filter (where it would blow up the parent mutation).
        try:
            pks.append(int(pk))
        except (TypeError, ValueError):
            continue

    if not pks:
        return []

    queryset = Profile.objects.filter(pk__in=pks)
    if exclude_profile is not None and exclude_profile.pk is not None:
        queryset = queryset.exclude(pk=exclude_profile.pk)
    return list(queryset)


def update_mentions(
    target_obj,
    mentioned_profile_ids: Iterable[str],
    exclude_profile: Optional["Profile"] = None,
):
    """Replace the Mention rows for ``target_obj`` with the resolved profile set.

    Mirrors ``m2m.set(...)`` semantics: inserts new, deletes removed, leaves
    unchanged rows untouched. Single public extension point for consumer
    mutations. Fires ``mentions_changed`` once per call (batched) with the
    delta lists.
    """
    Mention = swapper.load_model("baseapp_mentions", "Mention")

    profiles = resolve_mentioned_profiles(mentioned_profile_ids, exclude_profile=exclude_profile)
    new_pks = {p.pk for p in profiles}
    doc = DocumentId.get_or_create_for_object(target_obj)

    with transaction.atomic():
        existing = set(Mention.objects.filter(target=doc).values_list("profile_id", flat=True))
        to_remove = existing - new_pks
        to_add = new_pks - existing

        if to_remove:
            Mention.objects.filter(target=doc, profile_id__in=to_remove).delete()
        if to_add:
            Mention.objects.bulk_create(
                [Mention(target=doc, profile_id=pk) for pk in to_add],
                ignore_conflicts=True,
            )

        if to_add or to_remove:
            mentions_changed.send(
                sender=Mention,
                target=target_obj,
                added=list(to_add),
                removed=list(to_remove),
            )

    return list(Mention.objects.filter(target=doc).select_related("profile"))
