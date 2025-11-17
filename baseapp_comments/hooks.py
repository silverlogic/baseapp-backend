from baseapp_core.documents.models import DocumentId
from baseapp_core.events.decorators import register_hook

from .models import CommentStats, default_comments_count


@register_hook("document_created")
def handle_document_created(document_id: int, **kwargs):
    try:
        doc = DocumentId.objects.get(id=document_id)
        CommentStats.objects.get_or_create(
            target=doc, defaults={"comments_count": default_comments_count()}
        )
    except DocumentId.DoesNotExist:
        pass
