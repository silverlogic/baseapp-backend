import uuid

import pgtrigger
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import class_prepared
from django.dispatch import receiver
from model_utils.models import TimeStampedModel
from pgtrigger import utils


class PublicIdMapping(TimeStampedModel):
    """
    Centralized mapping of model instances to public IDs.
    """

    public_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Public-facing UUID identifier",
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, help_text="The model type this UUID maps to"
    )
    object_id = models.PositiveIntegerField(help_text="The primary key of the mapped object")
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        unique_together = ("content_type", "object_id")
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["public_id"]),
        ]
        verbose_name = "Public ID Mapping"
        verbose_name_plural = "Public ID Mappings"

    def __str__(self):
        return f"{self.content_type.model}:{self.object_id} -> {self.public_id}"

    @classmethod
    def get_or_create_public_id(cls, obj):
        if not obj or not obj.pk:
            return None, None

        mapping, created = cls.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk
        )
        return mapping.public_id, created

    @classmethod
    def get_object_by_public_id(cls, public_id, model_class=None):
        try:
            mapping = cls.objects.select_related("content_type").get(public_id=public_id)

            if model_class and mapping.content_type.model_class() != model_class:
                return None

            return mapping.content_object
        except cls.DoesNotExist:
            return None


class PublicIdMixin:
    """
    Mixin to add public ID functionality to any model.

    This mixin provides methods to work with public UUIDs for model instances.
    It automatically creates and manages mappings through the PublicIdMapping model.

    By extending this mixin, a new migration will be created to add the required pgtriggers to the model.
    """

    @property
    def public_id(self):
        """
        Get the public UUID for this instance.
        Creates a mapping if one doesn't exist.
        """
        from .models import PublicIdMapping

        public_id, created = PublicIdMapping.get_or_create_public_id(self)
        return public_id

    @classmethod
    def get_by_public_id(cls, public_id):
        from .models import PublicIdMapping

        return PublicIdMapping.get_object_by_public_id(public_id, cls)


class PublicIdFunc(pgtrigger.Func):
    """
    Reusable pgtrigger function for creating public id mapping triggers.
    """

    def render(self, model: models.Model) -> str:
        fields = utils.AttrDict({field.name: field for field in model._meta.fields})
        columns = utils.AttrDict({field.name: field.column for field in model._meta.fields})
        return self.func.format(
            model=model,
            meta=model._meta,
            fields=fields,
            columns=columns,
            public_id_mapping_table=PublicIdMapping._meta.db_table,
            content_type_table=ContentType._meta.db_table,
            pk=model._meta.pk.column,
        )


def delete_public_id_mapping_trigger():
    """
    Trigger to automatically delete the PublicIdMapping when a model using PublicIdMixin is deleted.
    """
    return pgtrigger.Trigger(
        name="delete_public_id_mapping",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Delete,
        func=PublicIdFunc(
            """
            DELETE FROM {public_id_mapping_table}
            WHERE
                content_type_id = (SELECT id FROM {content_type_table} WHERE app_label = '{meta.app_label}' AND model = '{meta.model_name}')
                AND object_id = OLD.{pk};
            RETURN NULL;
            """
        ),
    )


@receiver(class_prepared)
def add_public_id_trigger(sender, **kwargs):
    """
    Add the delete_public_id_mapping trigger to the model when it is prepared through the class_prepared signal.
    """
    # Only apply to concrete models that inherit from PublicIdMixin
    if not issubclass(sender, PublicIdMixin):
        return

    # Skip abstract models
    if sender._meta.abstract:
        return

    if not hasattr(sender._meta, "triggers"):
        sender._meta.triggers = []

    existing = [t.name for t in sender._meta.triggers]
    if "delete_public_id_mapping" not in existing:
        sender._meta.triggers.append(delete_public_id_mapping_trigger())
