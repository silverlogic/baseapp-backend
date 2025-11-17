from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from model_utils.models import TimeStampedModel


class DocumentId(TimeStampedModel):
    id = models.BigAutoField(primary_key=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, db_index=True)
    object_id = models.PositiveBigIntegerField(db_index=True)
    content_object = GenericForeignKey("content_type", "object_id")
    last_activity_at = models.DateTimeField(null=True, blank=True, auto_now=True)

    class Meta:
        unique_together = ("content_type", "object_id")
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]
        db_table = "baseapp_core_documentid"

    def __str__(self):
        return f"{self.content_type.model}:{self.object_id} -> {self.id}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            from baseapp_core.events.hooks import hook_manager

            hook_manager.emit("document_created", document_id=self.id)

    @classmethod
    def get_or_create_for_object(cls, obj):
        if not obj or not obj.pk:
            return None

        content_type = ContentType.objects.get_for_model(obj)
        document, _ = cls.objects.get_or_create(content_type=content_type, object_id=obj.pk)
        return document
