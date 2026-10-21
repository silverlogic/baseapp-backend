from __future__ import annotations

import swapper
from django.apps import apps
from django.db import models

from baseapp_core.plugins import SharedServiceProvider


class FilesMetadataService(SharedServiceProvider):
    """
    Service that provides files metadata (per-content-type counts dict + enabled
    flag) for any object that has a `DocumentId`. Registered in `apps.py`
    `ready()`. Mirrors `ReactableMetadataService`.
    """

    @property
    def service_name(self) -> str:
        return "files_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp.files")

    def _get_model(self):
        return swapper.load_model("baseapp_files", "FileTarget")

    def _default_counts(self) -> dict:
        from ..utils import default_files_count

        return default_files_count()

    def get_file_target(self, obj):
        """Return `FileTarget` for `obj`, or `None` if not found."""
        return self._get_model().get_for_object(obj)

    def get_or_create_file_target(self, obj):
        """Return or create `FileTarget` for `obj`."""
        from ..utils import get_or_create_file_target

        return get_or_create_file_target(obj)

    def get_files_count(self, obj) -> dict:
        """Return per-content-type files count dict for `obj`. Uses annotation if
        available; when the annotation is present but NULL (no FileTarget row exists
        yet) return the default counts dict immediately — no extra round-trip."""
        if hasattr(obj, "_file_target_files_count"):
            val = obj._file_target_files_count
            return val if val is not None else self._default_counts()
        file_target = self.get_file_target(obj)
        if file_target is not None:
            return file_target.files_count
        return self._default_counts()

    def is_files_enabled(self, obj) -> bool:
        """Return whether files are enabled for `obj`. Uses annotation if available."""
        if hasattr(obj, "_file_target_is_files_enabled"):
            val = obj._file_target_is_files_enabled
            return val if val is not None else True
        file_target = self.get_file_target(obj)
        return file_target.is_files_enabled if file_target else True

    def set_is_files_enabled(self, obj, value: bool) -> None:
        """Write-through setter for the `is_files_enabled` flag, creating the
        FileTarget row if needed."""
        file_target = self.get_or_create_file_target(obj)
        if file_target is not None:
            file_target.is_files_enabled = bool(value)
            file_target.save(update_fields=["is_files_enabled"])

    def annotate_queryset(self, queryset: models.QuerySet) -> models.QuerySet:
        return self._get_model().annotate_queryset(queryset)
