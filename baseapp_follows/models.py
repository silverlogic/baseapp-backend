import swapper
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel


class AbstractBaseFollow(TimeStampedModel, RelayModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="follows",
        on_delete=models.SET_NULL,
        null=True,
    )

    actor = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("actor"),
        related_name="following",
        on_delete=models.CASCADE,
    )

    target_is_following_back = models.BooleanField(default=False)

    target = models.ForeignKey(
        swapper.get_model_name("baseapp_profiles", "Profile"),
        verbose_name=_("target"),
        related_name="followers",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True

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
        # Check if the target is following the actor
        reciprocal_follow_exists = self.__class__.objects.filter(
            actor_id=self.target_id,
            target_id=self.actor_id,
        ).exists()

        self.target_is_following_back = reciprocal_follow_exists
        self.save(update_fields=["target_is_following_back"])

        if reciprocal_follow_exists:
            # Update the reciprocal follow instance
            reciprocal_follow = self.__class__.objects.get(
                actor_id=self.target_id,
                target_id=self.actor_id,
            )
            reciprocal_follow.target_is_following_back = True
            reciprocal_follow.save(update_fields=["target_is_following_back"])

    def delete(self, *args, **kwargs):
        actor = self.actor
        target = self.target
        super().delete(*args, **kwargs)

        self.update_followers_count(target)
        self.update_following_count(actor)
        self.update_target_is_following_back_on_delete()

    def update_target_is_following_back_on_delete(self):
        # Check if the target is following the actor
        reciprocal_follow = self.__class__.objects.filter(
            actor_id=self.target_id,
            target_id=self.actor_id,
        ).first()

        if reciprocal_follow:
            reciprocal_follow.target_is_following_back = False
            reciprocal_follow.save(update_fields=["target_is_following_back"])

    def update_followers_count(self, target):
        target.followers_count = target.followers.count()
        target.save(update_fields=["followers_count"])

    def update_following_count(self, actor):
        actor.following_count = actor.following.count()
        actor.save(update_fields=["following_count"])

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import FollowObjectType

        return FollowObjectType


class Follow(AbstractBaseFollow):
    class Meta:
        unique_together = [("actor", "target")]

        swappable = swapper.swappable_setting("baseapp_follows", "Follow")


class FollowableModel(models.Model):
    followers_count = models.PositiveIntegerField(default=0, editable=False)
    following_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
