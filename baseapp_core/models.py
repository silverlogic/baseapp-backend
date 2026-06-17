import os
import uuid

import pgtrigger
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import class_prepared
from django.dispatch import receiver
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.hashids.models import *  # noqa
from baseapp_core.models import *  # noqa


class CaseInsensitiveCharField(models.CharField):
    description = _("Case insensitive character")

    def db_type(self, connection):
        return "citext"


class CaseInsensitiveTextField(models.TextField):
    description = _("Case insensitive text")

    def db_type(self, connection):
        return "citext"


class CaseInsensitiveEmailField(CaseInsensitiveTextField, models.EmailField):
    description = _("Case insensitive email address")


@deconstructible
class random_name_in(object):
    def __init__(self, dir):
        self.dir = dir

    def __call__(self, instance, filename):
        ext = filename.split(".")[-1]
        filename = "{}.{}".format(uuid.uuid4(), ext)
        return os.path.join(self.dir, filename)


@deconstructible
class random_dir_in(object):
    """
    Upload a file to a directory with a randomly generated name, but keep the real file name.
    """

    def __init__(self, base_dir):
        self.base_dir = base_dir

    def __call__(self, instance, filename):
        return os.path.join(self.base_dir, str(uuid.uuid4()), filename)


class DocumentId(TimeStampedModel):
    """
    Centralized document registry for all entities in the system.

    This model serves as the single point of reference for entity identity,
    enabling decoupling of apps while maintaining system-wide unique identifiers.
    Part of the DocumentId pattern for plugin architecture.
    """

    public_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        help_text="Public-facing UUID identifier",
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, help_text="The model type this UUID maps to"
    )
    object_id = models.PositiveBigIntegerField(help_text="The primary key of the mapped object")
    content_object = GenericForeignKey("content_type", "object_id")

    class Meta:
        unique_together = ("content_type", "object_id")
        indexes = [
            models.Index(fields=["public_id"]),
        ]
        verbose_name = "Document ID"
        verbose_name_plural = "Document IDs"

    def __str__(self):
        return f"{self.content_type.model}:{self.object_id} -> {self.public_id}"

    @classmethod
    def get_public_id_from_object(cls, obj):
        if not obj or not obj.pk:
            return None

        try:
            mapping = cls.objects.get(
                content_type=ContentType.objects.get_for_model(obj), object_id=obj.pk
            )
            return mapping.public_id
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_object_by_public_id(cls, public_id, model_class=None):
        try:
            mapping = cls.objects.select_related("content_type").get(public_id=public_id)

            if model_class and mapping.content_type.model_class() != model_class:
                return None

            return mapping.content_object
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_content_type_and_id_by_public_id(cls, public_id) -> tuple[ContentType, int] | None:
        try:
            mapping = cls.objects.select_related("content_type").get(public_id=public_id)
            return mapping.content_type, mapping.object_id
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_or_create_for_object(cls, obj):
        """
        Return the DocumentId for the given object, creating it if it does not exist.

        When a new row is created, the document_created signal is sent (via post_save).
        """
        # TODO (plugin-arch): Cover with unit tests.
        if not obj or not obj.pk:
            return None

        ct = ContentType.objects.get_for_model(obj)
        doc, _ = cls.objects.get_or_create(content_type=ct, object_id=obj.pk)
        return doc


class DocumentIdMixin(models.Model):
    """
    Mixin to add document ID functionality to any model.

    This mixin provides methods to work with public UUIDs for model instances.
    It automatically creates and manages entries in the centralized DocumentId registry.

    By extending this mixin, a new migration will be created to add the required pgtriggers to the model.
    """

    # Reverse-GFK to this object's row in the DocumentId registry. Lets downstream
    # packages that key off DocumentId (mentions, follows, reactions, …) be
    # walked as standard `prefetch_related("document__<relation>")` chains
    # by the query optimizer, instead of falling back to per-row fetches.
    # Carries no DB column on this model, the join goes through DocumentId's
    # `(content_type, object_id)` GFK.
    document = GenericRelation(
        DocumentId,
        content_type_field="content_type",
        object_id_field="object_id",
    )

    class Meta:
        abstract = True

    @property
    def public_id(self):
        from baseapp_core.hashids.strategies import (
            get_hashids_strategy_from_instance_or_cls,
        )

        strategy = get_hashids_strategy_from_instance_or_cls(self)
        return strategy.id_resolver.get_id_from_instance(self)

    @classmethod
    def get_by_public_id(cls, public_id):
        from baseapp_core.hashids.strategies import (
            get_hashids_strategy_from_instance_or_cls,
        )

        strategy = get_hashids_strategy_from_instance_or_cls(cls)
        return strategy.id_resolver.resolve_id(public_id, model_cls=cls)


class DocumentIdUniqueTargetMixin(models.Model):
    """
    Base for models that hang a single row off a documentable object.

    The primary key is a one-to-one `target` to `DocumentId`, so there is at
    most one row per documentable object (one-to-one, unique per document).
    Provides lookup/creation helpers keyed by the documentable object itself
    rather than by its `DocumentId`.
    """

    target = models.OneToOneField(
        DocumentId,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True

    @classmethod
    def get_for_object(cls, obj: models.Model | None) -> "DocumentIdUniqueTargetMixin | None":
        """Return the row for the given object, or `None` if not found."""
        if not obj or not getattr(obj, "pk", None):
            return None
        try:
            ct = ContentType.objects.get_for_model(obj)
            return cls.objects.get(target__content_type=ct, target__object_id=obj.pk)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_or_create_for_object(
        cls, obj: models.Model | None
    ) -> "DocumentIdUniqueTargetMixin | None":
        """Return or create the row for the given object."""
        if not obj or not getattr(obj, "pk", None):
            return None
        doc_id = DocumentId.get_or_create_for_object(obj)
        if doc_id:
            instance, _ = cls.objects.get_or_create(target=doc_id)
            return instance
        return None


class DocumentIdTargetMixin(models.Model):
    """
    Base for models that point at a documentable object through a (non-unique)
    `target_document` foreign key — many rows may share the same `DocumentId`.

    Exposes a `target` property that transparently reads/writes the underlying
    object (creating its `DocumentId` on assignment), plus shortcuts to the
    target's content type and object id.
    """

    target_document = models.ForeignKey(
        DocumentId,
        verbose_name=_("target document"),
        blank=False,
        null=False,
        related_name="%(app_label)s_%(class)s",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True

    def _get_target(self):
        if not self.target_document_id:
            return None
        if hasattr(self, "_target_object_cache"):
            return self._target_object_cache
        self._target_object_cache = self.target_document.content_object
        return self._target_object_cache

    _get_target.short_description = _("target")

    def _set_target(self, value):
        if not value:
            self.target_document = None
            self._target_object_cache = None
            return
        self.target_document = DocumentId.get_or_create_for_object(value)
        self._target_object_cache = value

    target = property(_get_target, _set_target)

    @property
    def target_content_type(self):
        if self.target_document_id:
            return self.target_document.content_type
        return None

    @property
    def target_content_type_id(self):
        if self.target_document_id:
            return self.target_document.content_type_id
        return None

    @property
    def target_object_id(self):
        if self.target_document_id:
            return self.target_document.object_id
        return None


class DocumentIdFunc(pgtrigger.Func):
    """
    Reusable pgtrigger function for creating document ID triggers.
    """

    def render(
        self,
        meta=None,
        fields=None,
        columns=None,
        **kwargs,
    ) -> str:
        concrete_model = meta.concrete_model
        app_label = concrete_model._meta.app_config.label
        model_name = concrete_model._meta.model_name
        return self.func.format(
            model=meta.model,
            app_label=app_label,
            model_name=model_name,
            fields=fields,
            columns=columns,
            document_id_table=DocumentId._meta.db_table,
            content_type_table=ContentType._meta.db_table,
            pk=meta.pk.column,
        )


def insert_document_id_trigger():
    """
    Trigger to automatically insert a DocumentId when a model using DocumentIdMixin is inserted.
    """
    return pgtrigger.Trigger(
        name="insert_document_id",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Insert,
        func=DocumentIdFunc("""
            INSERT INTO {document_id_table} (public_id, content_type_id, object_id, created, modified)
            VALUES (
                gen_random_uuid(),
                (SELECT id FROM {content_type_table} WHERE app_label = '{app_label}' AND model = '{model_name}'),
                NEW.{pk},
                NOW(),
                NOW()
            )
            ON CONFLICT (content_type_id, object_id) DO NOTHING;
            RETURN NULL;
            """),
    )


def delete_document_id_trigger():
    """
    Trigger to automatically delete the DocumentId when a model using DocumentIdMixin is deleted.
    """
    return pgtrigger.Trigger(
        name="delete_document_id",
        level=pgtrigger.Row,
        when=pgtrigger.After,
        operation=pgtrigger.Delete,
        func=DocumentIdFunc("""
            DELETE FROM {document_id_table}
            WHERE
                content_type_id = (SELECT id FROM {content_type_table} WHERE app_label = '{app_label}' AND model = '{model_name}')
                AND object_id = OLD.{pk};
            RETURN NULL;
            """),
    )


@receiver(class_prepared)
def add_document_id_trigger(sender, **kwargs):
    """
    Add the document ID triggers to the model when it is prepared through the class_prepared signal.
    """
    # Only models that inherit from DocumentIdMixin
    if not issubclass(sender, DocumentIdMixin):
        return

    # Skip non-schema models
    if sender._meta.abstract or sender._meta.proxy:
        return

    # Skip swapped-out models
    if sender._meta.swapped:
        return

    if not hasattr(sender._meta, "triggers"):
        sender._meta.triggers = []

    existing = [t.name for t in sender._meta.triggers]
    if "insert_document_id" not in existing:
        sender._meta.triggers.append(insert_document_id_trigger())
    if "delete_document_id" not in existing:
        sender._meta.triggers.append(delete_document_id_trigger())


# Every baseapp_core model coming from internal folders should be added here
from baseapp_core.hashids.models import LegacyWithPkMixin  # noqa
