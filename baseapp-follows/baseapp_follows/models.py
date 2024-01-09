import swapper
from baseapp_core.graphql.models import RelayModel
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from model_utils.models import TimeStampedModel


class AbstractBaseFollow(TimeStampedModel, RelayModel):
    actor_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name="actor_follows",
    )
    actor_object_id = models.PositiveIntegerField(blank=True, null=True)
    actor = GenericForeignKey("actor_content_type", "actor_object_id")

    target_is_following_back = models.BooleanField(default=False)

    target_content_type = models.ForeignKey(
        ContentType,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        db_index=True,
    )
    target_object_id = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["actor_content_type", "actor_object_id"]),
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

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
        reciprocal_follow_exists = Follow.objects.filter(
            actor_content_type=ContentType.objects.get_for_model(self.target),
            actor_object_id=self.target.id,
            target_content_type=ContentType.objects.get_for_model(self.actor),
            target_object_id=self.actor.id,
        ).exists()

        self.target_is_following_back = reciprocal_follow_exists
        self.save(update_fields=["target_is_following_back"])

        if reciprocal_follow_exists:
            # Update the reciprocal follow instance
            reciprocal_follow = Follow.objects.get(
                actor_content_type=ContentType.objects.get_for_model(self.target),
                actor_object_id=self.target.id,
                target_content_type=ContentType.objects.get_for_model(self.actor),
                target_object_id=self.actor.id,
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
        reciprocal_follow = Follow.objects.filter(
            actor_content_type=ContentType.objects.get_for_model(self.target),
            actor_object_id=self.target.id,
            target_content_type=ContentType.objects.get_for_model(self.actor),
            target_object_id=self.actor.id,
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


class Follow(AbstractBaseFollow):
    class Meta:
        unique_together = [
            ("actor_content_type", "actor_object_id", "target_content_type", "target_object_id")
        ]

        swappable = swapper.swappable_setting("baseapp_follows", "Follow")


SwappableFollow = swapper.load_model(
    "baseapp_follows", "Follow", required=False, require_ready=False
)


class FollowableModel(models.Model):
    followers = GenericRelation(
        SwappableFollow,
        content_type_field="target_content_type",
        object_id_field="target_object_id",
    )
    following = GenericRelation(
        SwappableFollow,
        content_type_field="actor_content_type",
        object_id_field="actor_object_id",
    )
    followers_count = models.PositiveIntegerField(default=0, editable=False)
    following_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
