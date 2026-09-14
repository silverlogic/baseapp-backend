from __future__ import annotations

from typing import TYPE_CHECKING

import swapper
from django.apps import apps

from baseapp_core.plugins import SharedServiceProvider

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from .models import AbstractRatableMetadata


class RatableMetadataService(SharedServiceProvider):
    """
    Service that provides rating metadata (count / sum / average / enabled flag)
    for any object that has a `DocumentId`. Registered in `apps.py` `ready()`.
    """

    @property
    def service_name(self) -> str:
        return "ratable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_ratings")

    def _get_model(self) -> type[AbstractRatableMetadata]:
        return swapper.load_model("baseapp_ratings", "RatableMetadata")

    def get_metadata(self, obj) -> AbstractRatableMetadata | None:
        """Return `RatableMetadata` for `obj`, or `None` if not found."""
        return self._get_model().get_for_object(obj)

    def get_or_create_metadata(self, obj) -> AbstractRatableMetadata | None:
        """Return or create `RatableMetadata` for `obj`."""
        return self._get_model().get_or_create_for_object(obj)

    def get_ratings_count(self, obj) -> int:
        """Return ratings count for obj. Use annotation if available."""
        if hasattr(obj, "_ratable_ratings_count"):
            val = obj._ratable_ratings_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.ratings_count if metadata else 0

    def get_ratings_sum(self, obj) -> int:
        """Return ratings sum for obj. Use annotation if available."""
        if hasattr(obj, "_ratable_ratings_sum"):
            val = obj._ratable_ratings_sum
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.ratings_sum if metadata else 0

    def get_ratings_average(self, obj) -> float:
        """Return ratings average for obj. Use annotation if available."""
        if hasattr(obj, "_ratable_ratings_average"):
            val = obj._ratable_ratings_average
            return val if val is not None else 0.0
        metadata = self.get_metadata(obj)
        return metadata.ratings_average if metadata else 0.0

    def is_ratings_enabled(self, obj) -> bool:
        """Return whether ratings are enabled for obj. Uses annotation if available."""
        if hasattr(obj, "_ratable_is_ratings_enabled"):
            val = obj._ratable_is_ratings_enabled
            return val if val is not None else True
        metadata = self.get_metadata(obj)
        return metadata.is_ratings_enabled if metadata else True

    def annotate_queryset(self, queryset) -> QuerySet:
        return self._get_model().annotate_queryset(queryset)
