import swapper
from baseapp_core.graphql.models import RelayModel

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from model_utils.models import TimeStampedModel


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
    #     settings.AUTH_USER_MODEL,
    #     on_delete=models.SET_NULL, # because blocks are from profiles, if a user is delete we don't want to delete the block, only if profile are deleted
    #     related_name="social_blocks",
    #     null=True,
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
