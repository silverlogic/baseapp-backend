from __future__ import annotations

import swapper
from django.apps import apps

from baseapp_core.plugins import SharedServiceProvider


class FollowableMetadataService(SharedServiceProvider):
    """
    Service that provides followable metadata (followers/following counts) for any object
    that has a `DocumentId`. Registered in `apps.py` `ready()`.

    Mirrors `baseapp_comments.CommentableMetadataService` so resolvers and
    `pre_optimization_hook` consumers can stay consistent across packages.
    """

    @property
    def service_name(self) -> str:
        return "followable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_follows")

    def _get_model(self):
        return swapper.load_model("baseapp_follows", "FollowableMetadata")

    def get_metadata(self, obj):
        """Return `FollowableMetadata` for `obj`, or `None` if not found."""
        return self._get_model().get_for_object(obj)

    def get_or_create_metadata(self, obj):
        """Return or create `FollowableMetadata` for `obj`."""
        return self._get_model().get_or_create_for_object(obj)

    def get_followers_count(self, obj) -> int:
        """Return followers count for `obj`. Uses annotation if available."""
        if hasattr(obj, "_followable_followers_count"):
            val = obj._followable_followers_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.followers_count if metadata else 0

    def get_following_count(self, obj) -> int:
        """Return following count for `obj`. Uses annotation if available."""
        if hasattr(obj, "_followable_following_count"):
            val = obj._followable_following_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.following_count if metadata else 0

    def annotate_queryset(self, queryset):
        """Annotate `queryset` with followable metadata for N+1 prevention."""
        return self._get_model().annotate_queryset(queryset)
