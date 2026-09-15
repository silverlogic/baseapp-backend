from __future__ import annotations

from typing import TYPE_CHECKING

import swapper
from django.apps import apps

from baseapp_core.plugins import SharedServiceProvider

from .models import default_reports_count

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet


class ReportableMetadataService(SharedServiceProvider):
    """
    Service that provides reportable metadata (per-type report counts) for any object
    that has a `DocumentId`. Registered in `apps.py` `ready()`.

    Mirrors `baseapp_comments.CommentableMetadataService` and
    `baseapp_follows.FollowableMetadataService` so resolvers and
    `pre_optimization_hook` consumers can stay consistent across packages.
    """

    @property
    def service_name(self) -> str:
        return "reportable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_reports")

    def _get_model(self) -> type[Model]:
        return swapper.load_model("baseapp_reports", "ReportableMetadata")

    def get_metadata(self, obj) -> Model | None:
        """Return `ReportableMetadata` for `obj`, or `None` if not found."""
        return self._get_model().get_for_object(obj)

    def get_or_create_metadata(self, obj) -> Model | None:
        """Return or create `ReportableMetadata` for `obj`."""
        return self._get_model().get_or_create_for_object(obj)

    def get_reports_count(self, obj) -> dict:
        """Return reports count dict for `obj`. Uses annotation if available."""
        if hasattr(obj, "_reportable_reports_count"):
            val = obj._reportable_reports_count
            return val if val is not None else default_reports_count()
        metadata = self.get_metadata(obj)
        return metadata.reports_count if metadata else default_reports_count()

    def annotate_queryset(self, queryset) -> QuerySet:
        """Annotate `queryset` with reportable metadata for N+1 prevention."""
        return self._get_model().annotate_queryset(queryset)
