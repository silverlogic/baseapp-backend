import swapper
from baseapp_core.graphql.models import RelayModel

# from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from model_utils.models import TimeStampedModel

# User = get_user_model()


class AbstractBaseBlock(TimeStampedModel, RelayModel):
    actor_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="actor_blocks",
    )
    actor_object_id = models.PositiveIntegerField(blank=True, null=True)
    actor = GenericForeignKey("actor_content_type", "actor_object_id")

    target_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        db_index=True,
    )
    target_object_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    # user = models.ForeignKey(
    #     User,
    #     on_delete=models.CASCADE,
    #     related_name="blocks",
    # )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["actor_content_type", "actor_object_id"]),
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

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

    def update_blockers_count(self, target):
        target.blockers_count = target.blockers.count()
        target.save(update_fields=["blockers_count"])

    def update_blocking_count(self, actor):
        actor.blocking_count = actor.blocking.count()
        actor.save(update_fields=["blocking_count"])


class Block(AbstractBaseBlock):
    class Meta:
        unique_together = [
            ("actor_content_type", "actor_object_id", "target_content_type", "target_object_id")
        ]

        swappable = swapper.swappable_setting("baseapp_blocks", "Block")


SwappableBlock = swapper.load_model("baseapp_blocks", "Block", required=False, require_ready=False)


class BlockableModel(models.Model):
    blockers = GenericRelation(
        SwappableBlock,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )
    blocking = GenericRelation(
        SwappableBlock,
        content_type_field="actor_content_type",
        object_id_field="actor_object_id",
    )
    blockers_count = models.PositiveIntegerField(default=0, editable=False)
    blocking_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
