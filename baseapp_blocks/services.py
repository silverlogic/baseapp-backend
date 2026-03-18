from __future__ import annotations

from django.apps import apps
from django.db import models

from baseapp_core.plugins import SharedServiceProvider


class BlockLookupService(SharedServiceProvider):
    @property
    def service_name(self) -> str:
        return "blocks.lookup"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_blocks")

    def exclude_blocked_from_foreign_queryset(
        self, queryset: models.QuerySet, user: models.Model
    ) -> models.QuerySet:
        if not user or user.is_anonymous:
            return queryset

        if apps.is_installed("baseapp_profiles"):
            profile = getattr(user, "current_profile", None)
            if not profile:
                return queryset

            blocked_profile_ids = profile.blocking.values_list("target_id", flat=True)
            blocker_profile_ids = profile.blockers.values_list("actor_id", flat=True)
            return queryset.exclude(profile__id__in=blocked_profile_ids).exclude(
                profile__id__in=blocker_profile_ids
            )

        blocked_user_ids = user.social_blocks.values_list("target_id", flat=True)
        blocker_user_ids = user.blockers.values_list("user_id", flat=True)
        return queryset.exclude(user__id__in=blocked_user_ids).exclude(
            user__id__in=blocker_user_ids
        )
