from __future__ import annotations

import swapper
from django.apps import apps
from django.db import models
from django.db.models import Q
from query_optimizer.typing import GQLInfo

from baseapp_core.plugins import SharedServiceProvider

# Hint key set by _exclude_blocked_from_foreign_queryset so get_queryset() knows
# filtering was already applied and can skip a redundant .exclude().
_BLOCKED_PROFILES_FILTERED_HINT = "_blocked_profiles_filtered"


class BlockLookupService(SharedServiceProvider):
    @property
    def service_name(self) -> str:
        return "blocks.lookup"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_blocks")

    def exclude_blocked_from_foreign_queryset(
        self, queryset: models.QuerySet, info: GQLInfo
    ) -> models.QuerySet:
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

        if apps.is_installed("baseapp_profiles"):
            profile = getattr(user, "current_profile", None)
            if profile:
                blocked_profile_ids = profile.blocking.values_list("target_id", flat=True)
                blocker_profile_ids = profile.blockers.values_list("actor_id", flat=True)
            else:
                # Fallback for contexts where middleware did not set current_profile:
                # apply the union of block relations for all profiles owned by the user.
                Profile = swapper.load_model("baseapp_profiles", "Profile")
                owned_profiles = Profile.objects.filter(owner=user)
                blocked_profile_ids = owned_profiles.values_list("blocking__target_id", flat=True)
                blocker_profile_ids = owned_profiles.values_list("blockers__actor_id", flat=True)

            qs = queryset.exclude(
                Q(profile__id__in=blocked_profile_ids) | Q(profile__id__in=blocker_profile_ids)
            )
            qs._hints[_BLOCKED_PROFILES_FILTERED_HINT] = True
            return qs

        blocked_user_ids = user.social_blocks.values_list("target_id", flat=True)
        blocker_user_ids = user.blockers.values_list("user_id", flat=True)
        qs = queryset.exclude(Q(user__id__in=blocked_user_ids) | Q(user__id__in=blocker_user_ids))
        qs._hints[_BLOCKED_PROFILES_FILTERED_HINT] = True
        return qs


class BlockableMetadataService(SharedServiceProvider):
    """
    Service that provides blockable metadata (blockers / blocking counts) for
    any object that has a `DocumentId`. Registered in `apps.py` via
    `register_shared_services`.
    """

    @property
    def service_name(self) -> str:
        return "blockable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_blocks")

    def _get_model(self):
        return swapper.load_model("baseapp_blocks", "BlockableMetadata")

    def get_metadata(self, obj):
        """Return `BlockableMetadata` for `obj`, or `None` if not found."""
        return self._get_model().get_for_object(obj)

    def get_or_create_metadata(self, obj):
        """Return or create `BlockableMetadata` for `obj`."""
        return self._get_model().get_or_create_for_object(obj)

    def get_blockers_count(self, obj) -> int:
        """Return number of blocks where `obj` is the target. Uses annotation if available."""
        if hasattr(obj, "_blockable_blockers_count"):
            val = obj._blockable_blockers_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.blockers_count if metadata else 0

    def get_blocking_count(self, obj) -> int:
        """Return number of blocks where `obj` is the actor. Uses annotation if available."""
        if hasattr(obj, "_blockable_blocking_count"):
            val = obj._blockable_blocking_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.blocking_count if metadata else 0

    def recompute_blockers_count(self, target) -> None:
        """Recount blocks where `target` is the target and write through to the metadata row."""
        if not target or not getattr(target, "pk", None):
            return
        metadata = self.get_or_create_metadata(target)
        if metadata is None:
            return
        # The reverse manager `blockers` is provided by ProfileMixin (or UserMixin) on
        # the consumer model — its name is stable across profile / user paths.
        count = target.blockers.count() if hasattr(target, "blockers") else 0
        if metadata.blockers_count != count:
            metadata.blockers_count = count
            metadata.save(update_fields=["blockers_count", "modified"])

    def recompute_blocking_count(self, actor) -> None:
        """Recount blocks where `actor` is the actor and write through to the metadata row."""
        if not actor or not getattr(actor, "pk", None):
            return
        metadata = self.get_or_create_metadata(actor)
        if metadata is None:
            return
        count = actor.blocking.count() if hasattr(actor, "blocking") else 0
        if metadata.blocking_count != count:
            metadata.blocking_count = count
            metadata.save(update_fields=["blocking_count", "modified"])

    def annotate_queryset(self, queryset):
        return self._get_model().annotate_queryset(queryset)
