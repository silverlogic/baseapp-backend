from __future__ import annotations

import swapper
from django.apps import apps

from baseapp_core.plugins import SharedServiceProvider


class ReactableMetadataService(SharedServiceProvider):
    """
    Service that provides reaction metadata (per-type counts dict + enabled
    flag) for any object that has a `DocumentId`. Registered in `apps.py`
    `ready()`.
    """

    @property
    def service_name(self) -> str:
        return "reactable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_reactions")

    def _get_model(self):
        return swapper.load_model("baseapp_reactions", "ReactableMetadata")

    def _default_counts(self) -> dict:
        from .models import default_reactions_count

        return default_reactions_count()

    def get_metadata(self, obj):
        """Return `ReactableMetadata` for `obj`, or `None` if not found."""
        return self._get_model().get_for_object(obj)

    def get_or_create_metadata(self, obj):
        """Return or create `ReactableMetadata` for `obj`."""
        return self._get_model().get_or_create_for_object(obj)

    def get_reactions_count(self, obj) -> dict:
        """Return per-type reactions count dict for `obj`. Use annotation if available.
        When the annotation is present but NULL (no metadata row exists yet) we return
        the default counts dict immediately — no extra round-trip — same shape as
        ratings' `get_ratings_count` which short-circuits on annotation presence."""
        if hasattr(obj, "_reactable_reactions_count"):
            val = obj._reactable_reactions_count
            return val if val is not None else self._default_counts()
        metadata = self.get_metadata(obj)
        if metadata is not None:
            return metadata.reactions_count
        return self._default_counts()

    def is_reactions_enabled(self, obj) -> bool:
        """Return whether reactions are enabled for `obj`. Uses annotation if available."""
        if hasattr(obj, "_reactable_is_reactions_enabled"):
            val = obj._reactable_is_reactions_enabled
            return val if val is not None else True
        metadata = self.get_metadata(obj)
        return metadata.is_reactions_enabled if metadata else True

    def set_is_reactions_enabled(self, obj, value: bool) -> None:
        """Convenience setter for mutations that accept `is_reactions_enabled` input.
        Writes through to the metadata row, creating it if needed."""
        metadata = self.get_or_create_metadata(obj)
        if metadata is not None:
            metadata.is_reactions_enabled = bool(value)
            metadata.save(update_fields=["is_reactions_enabled", "modified"])

    def annotate_queryset(self, queryset):
        return self._get_model().annotate_queryset(queryset)
