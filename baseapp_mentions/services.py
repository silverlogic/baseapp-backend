from typing import Iterable, List, Optional

import swapper

from baseapp_core.graphql.utils import get_pk_from_relay_id

Profile = swapper.load_model("baseapp_profiles", "Profile")


def resolve_mentioned_profiles(
    mentioned_profile_ids: Iterable[str],
    exclude_profile: Optional["Profile"] = None,
) -> List["Profile"]:
    """Resolve Relay global IDs to Profile instances, filtering out self-mention.

    Silently drops malformed or stale IDs so a flaky client reference does not
    break the parent mutation. Returns a list (not a queryset) because the
    caller passes it to `instance.mentioned_profiles.set(...)`.
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
