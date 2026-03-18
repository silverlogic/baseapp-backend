import swapper
from django.apps import apps
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin
from baseapp_core.plugins import apply_if_installed

inheritances = []

if apps.is_installed("baseapp_profiles"):
    ProfileModel = swapper.get_model_name("baseapp_profiles", "Profile")

    class ProfileMixin(models.Model):
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

        class Meta:
            abstract = True

    inheritances.append(ProfileMixin)
else:

    class UserMixin(models.Model):
        target = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            verbose_name=_("blockers"),
            related_name="blockers",
            on_delete=models.CASCADE,
            null=True,
            blank=True,
        )

        class Meta:
            abstract = True

    inheritances.append(UserMixin)


class AbstractBaseBlock(*inheritances, DocumentIdMixin, RelayModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=apply_if_installed(
            "baseapp_profiles",
            models.SET_NULL,  # blocks come from profiles when profiles app is enabled
            models.CASCADE,
        ),
        related_name=apply_if_installed(
            "baseapp_profiles",
            "blocking",
            "social_blocks",
        ),
        null=True,
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(
                fields=(
                    ["target", "actor"]
                    if apps.is_installed("baseapp_profiles")
                    else ["target", "user"]
                )
            ),
        ]

    def __str__(self):
        actor = self.actor if apps.is_installed("baseapp_profiles") else self.user
        return "{} blocked {}".format(actor, self.target)

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)  # Save the instance first

        if created:
            actor = self.actor if apps.is_installed("baseapp_profiles") else self.user
            self.update_blockers_count(self.target)
            self.update_blocking_count(actor)

    def delete(self, *args, **kwargs):
        actor = self.actor if apps.is_installed("baseapp_profiles") else self.user
        target = self.target
        super().delete(*args, **kwargs)

        self.update_blockers_count(target)
        self.update_blocking_count(actor)

    def update_blockers_count(self, target):
        if not target or not hasattr(target, "blockers_count"):
            return
        target.blockers_count = target.blockers.count()
        target.save(update_fields=["blockers_count"])

    def update_blocking_count(self, actor):
        if not actor or not hasattr(actor, "blocking_count"):
            return
        actor.blocking_count = actor.blocking.count()
        actor.save(update_fields=["blocking_count"])
