import swapper
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel


class AbstractBaseBlock(TimeStampedModel, RelayModel):
    actor = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("blocking"),
        related_name="blocking",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    target = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("blockers"),
        related_name="blockers",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,  # because blocks are from profiles, if a user is delete we don't want to delete the block, only if profile are deleted
        related_name="blocking",
        null=True,
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["target", "actor"]),
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
