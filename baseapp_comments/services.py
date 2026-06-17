from __future__ import annotations

import swapper
from django.apps import apps

from baseapp_core.plugins import SharedServiceProvider

from .models import default_comments_count


class CommentableMetadataService(SharedServiceProvider):
    """
    Service that provides commentable metadata (comments count, enabled flag)
    for any object that has a DocumentId. Registered in apps.py ready().
    """

    @property
    def service_name(self) -> str:
        return "commentable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_comments")

    def _get_model(self):
        return swapper.load_model("baseapp_comments", "CommentableMetadata")

    def get_metadata(self, obj):
        """Return CommentableMetadata for obj, or None if not found."""
        CommentableMetadata = self._get_model()
        return CommentableMetadata.get_for_object(obj)

    def get_or_create_metadata(self, obj):
        """Return or create CommentableMetadata for obj."""
        CommentableMetadata = self._get_model()
        return CommentableMetadata.get_or_create_for_object(obj)

    def is_comments_enabled(self, obj) -> bool:
        """Return whether comments are enabled for obj. Uses annotation if available."""
        if hasattr(obj, "_commentable_is_comments_enabled"):
            val = obj._commentable_is_comments_enabled
            return val if val is not None else True
        metadata = self.get_metadata(obj)
        return metadata.is_comments_enabled if metadata else True

    def get_comments_count(self, obj) -> dict:
        """Return comments count dict for obj. Uses annotation if available."""
        if hasattr(obj, "_commentable_comments_count"):
            val = obj._commentable_comments_count
            return val if val is not None else default_comments_count()
        metadata = self.get_metadata(obj)
        return metadata.comments_count if metadata else default_comments_count()

    def annotate_queryset(self, queryset):
        """Annotate queryset with commentable metadata for N+1 prevention."""
        CommentableMetadata = self._get_model()
        return CommentableMetadata.annotate_queryset(queryset)
