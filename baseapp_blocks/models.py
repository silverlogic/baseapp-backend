import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin, DocumentIdUniqueTargetMixin
from baseapp_core.plugins import shared_services

ProfileModel = swapper.get_model_name("baseapp_profiles", "Profile")


class AbstractBlock(DocumentIdMixin, RelayModel, TimeStampedModel):
    actor = models.ForeignKey(
        ProfileModel,
        verbose_name=_("blocking"),
        related_name="blocking",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    target = models.ForeignKey(
        ProfileModel,
        verbose_name=_("blockers"),
        related_name="blockers",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="blocking",
        null=True,
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_blocks", "Block")
        indexes = [models.Index(fields=["target", "actor"])]
        unique_together = [("actor", "target")]

    def __str__(self):
        return "{} blocked {}".format(self.actor, self.target)

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)  # Save the instance first

        if created:
            self.update_blockers_count(self.target)
            self.update_blocking_count(self.actor)

    def delete(self, *args, **kwargs):
        actor = self.actor
        target = self.target
        super().delete(*args, **kwargs)

        self.update_blockers_count(target)
        self.update_blocking_count(actor)

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import BlockObjectType

        return BlockObjectType

    def update_blockers_count(self, target):
        if not target:
            return
        service = shared_services.get("blockable_metadata")
        if service is None:
            return
        service.recompute_blockers_count(target)

    def update_blocking_count(self, actor):
        if not actor:
            return
        service = shared_services.get("blockable_metadata")
        if service is None:
            return
        service.recompute_blocking_count(actor)


class AbstractBlockableMetadata(DocumentIdUniqueTargetMixin, TimeStampedModel):
    """
    Stores blockable metadata (blocker / blocking counts) for any documentable object.
    Currently, blocks are only implemented for profiles. Nevertheless, this follows
    the plugin architecture, allowing us to easily extend blocks to other models.
    """

    blockers_count = models.PositiveIntegerField(default=0, editable=False)
    blocking_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_blocks", "BlockableMetadata")
        verbose_name = _("blockable metadata")
        verbose_name_plural = _("blockable metadata")

    def __str__(self):
        return f"BlockableMetadata for {self.target}"

    @classmethod
    def annotate_queryset(cls, queryset):
        """
        Annotate `queryset` with blockable metadata so resolvers don't N+1.
        Adds `_blockable_blockers_count` and `_blockable_blocking_count`,
        both `Coalesce`'d to 0 so consumer-side ORDER BY can sort on a real
        expression.
        """
        model_cls = queryset.model
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        metadata_qs = cls.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        return queryset.annotate(
            _blockable_blockers_count=Coalesce(
                Subquery(
                    metadata_qs.values("blockers_count")[:1],
                    output_field=models.PositiveIntegerField(),
                ),
                Value(0),
            ),
            _blockable_blocking_count=Coalesce(
                Subquery(
                    metadata_qs.values("blocking_count")[:1],
                    output_field=models.PositiveIntegerField(),
                ),
                Value(0),
            ),
        )
