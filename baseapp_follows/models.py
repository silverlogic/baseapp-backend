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

    class ProfileMixin(models.Model):
        actor = models.ForeignKey(
            swapper.get_model_name("baseapp_profiles", "Profile"),
            verbose_name=_("actor"),
            related_name="following",
            on_delete=models.CASCADE,
        )

        target = models.ForeignKey(
            swapper.get_model_name("baseapp_profiles", "Profile"),
            verbose_name=_("target"),
            related_name="followers",
            on_delete=models.CASCADE,
        )

        class Meta:
            abstract = True

    inheritances.append(ProfileMixin)
else:

    class UserTargetMixin(models.Model):
        target = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            verbose_name=_("target"),
            related_name="followers",
            on_delete=models.CASCADE,
        )

        @property
        def actor(self):
            return self.user

        @actor.setter
        def actor(self, value):
            self.user = value

        @property
        def actor_id(self):
            return self.user_id

        @actor_id.setter
        def actor_id(self, value):
            self.user_id = value

        class Meta:
            abstract = True

    inheritances.append(UserTargetMixin)


class AbstractBaseFollow(*inheritances, TimeStampedModel, DocumentIdMixin, RelayModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name=apply_if_installed(
            "baseapp_profiles",
            "follows",
            "following",
        ),
        on_delete=models.SET_NULL,
        null=True,
    )

    target_is_following_back = models.BooleanField(default=False)

    class Meta:
        unique_together = [
            apply_if_installed(
                "baseapp_profiles",
                ("actor", "target"),
                ("user", "target"),
            )
        ]
        swappable = swapper.swappable_setting("baseapp_follows", "Follow")
        abstract = True

    def _reciprocal_filter(self) -> dict:
        return {
            apply_if_installed("baseapp_profiles", "actor_id", "user_id"): self.target_id,
            "target_id": self.actor_id,
        }

    def __str__(self):
        return "{} followed {}".format(self.actor, self.target)

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)  # Save the instance first

        if created:
            self.update_followers_count(self.target)
            self.update_following_count(self.actor)
            self.update_target_is_following_back()  # Check for reciprocal relationship after saving

    def update_target_is_following_back(self):
        reciprocal_filter = self._reciprocal_filter()
        reciprocal_follow_exists = self.__class__.objects.filter(**reciprocal_filter).exists()

        self.target_is_following_back = reciprocal_follow_exists
        self.save(update_fields=["target_is_following_back"])

        if reciprocal_follow_exists:
            # Update the reciprocal follow instance
            reciprocal_follow = self.__class__.objects.get(**reciprocal_filter)
            reciprocal_follow.target_is_following_back = True
            reciprocal_follow.save(update_fields=["target_is_following_back"])

    def delete(self, *args, **kwargs):
        target = self.target
        super().delete(*args, **kwargs)

        self.update_followers_count(target)
        self.update_following_count(self.actor)
        self.update_target_is_following_back_on_delete()

    def update_target_is_following_back_on_delete(self):
        reciprocal_filter = self._reciprocal_filter()
        reciprocal_follow = self.__class__.objects.filter(**reciprocal_filter).first()

        if reciprocal_follow:
            reciprocal_follow.target_is_following_back = False
            reciprocal_follow.save(update_fields=["target_is_following_back"])

    def update_followers_count(self, target):
        if not target or not hasattr(target, "followers_count"):
            return
        target.followers_count = target.followers.count()
        target.save(update_fields=["followers_count"])

    def update_following_count(self, actor):
        if not actor or not hasattr(actor, "following_count"):
            return
        actor.following_count = actor.following.count()
        actor.save(update_fields=["following_count"])

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import FollowObjectType

        return FollowObjectType


class Follow(AbstractBaseFollow):
    class Meta(AbstractBaseFollow.Meta):
        pass


class FollowableModel(models.Model):
    followers_count = models.PositiveIntegerField(default=0, editable=False)
    following_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
