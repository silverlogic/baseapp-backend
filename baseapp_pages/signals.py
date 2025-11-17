# TODO: Review this, since we can use pgtrigger to create the document id.
import swapper
from django.db.models.signals import post_save

from baseapp_core.documents.models import DocumentId

Page = swapper.load_model("baseapp_pages", "Page")


def ensure_document_id(sender, instance, created, **kwargs):
    DocumentId.get_or_create_for_object(instance)


post_save.connect(ensure_document_id, sender=Page, dispatch_uid="baseapp_pages_ensure_document_id")
