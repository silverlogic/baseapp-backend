from django.apps import apps

from baseapp_core.documents.models import DocumentId
from baseapp_core.services.registry import ServiceProvider

from .models import CommentStats


class CommentsCountService(ServiceProvider):
    @property
    def service_name(self) -> str:
        return "comments_count"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_comments")

    def get_count(self, document_id: int) -> dict:
        try:
            doc = DocumentId.objects.get(id=document_id)
            stats = CommentStats.objects.get(target=doc)
            return stats.comments_count
        except (DocumentId.DoesNotExist, CommentStats.DoesNotExist):
            return {"total": 0, "main": 0, "replies": 0, "pinned": 0, "reported": 0}

    def is_enabled(self, document_id: int) -> bool:
        try:
            doc = DocumentId.objects.get(id=document_id)
            stats = CommentStats.objects.get(target=doc)
            return stats.is_comments_enabled
        except (DocumentId.DoesNotExist, CommentStats.DoesNotExist):
            return False
