from __future__ import annotations

from django.apps import apps
from django.db import models
from django.db.models import Q
from query_optimizer.typing import GQLInfo

from baseapp_core.plugins import SharedServiceProvider

# Hint key set by _exclude_blocked_profiles so get_queryset() knows
# filtering was already applied and can skip a redundant .exclude().
_BLOCKED_PROFILES_FILTERED_HINT = "_blocked_profiles_filtered"


class BlockLookupService(SharedServiceProvider):
    @property
    def service_name(self) -> str:
        return "blocks.lookup"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_blocks")

    def exclude_blocked_profiles(self, queryset: models.QuerySet, info: GQLInfo) -> models.QuerySet:
        """Exclude comments from blocked/blocking profiles.

        Must be called BEFORE evaluate_with_prefetch_hack / optimize
        so that .exclude() cloning doesn't destroy the result cache.
        Sets ``_BLOCKED_PROFILES_FILTERED_HINT`` on the queryset so
        ``get_queryset()`` knows filtering was already applied.
        """
        # TODO (plugin-arch): Cover this with unit tests
        if queryset._hints.get(_BLOCKED_PROFILES_FILTERED_HINT):
            return queryset

        user = info.context.user
        if user.is_anonymous:
            queryset._hints[_BLOCKED_PROFILES_FILTERED_HINT] = True
            return queryset

        profile = getattr(user, "current_profile", None)
        if not profile:
            queryset._hints[_BLOCKED_PROFILES_FILTERED_HINT] = True
            return queryset

        blocked_profile_ids = profile.blocking.values_list("target_id", flat=True)
        blocker_profile_ids = profile.blockers.values_list("actor_id", flat=True)

        qs = queryset.exclude(
            Q(profile__id__in=blocked_profile_ids) | Q(profile__id__in=blocker_profile_ids)
        )
        qs._hints[_BLOCKED_PROFILES_FILTERED_HINT] = True
        return qs
