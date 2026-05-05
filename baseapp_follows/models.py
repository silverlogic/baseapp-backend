import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentId, DocumentIdMixin


class AbstractFollowableMetadata(TimeStampedModel):
    target = models.OneToOneField(
        DocumentId,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="followable_metadata",
    )
    followers_count = models.PositiveIntegerField(default=0, editable=False)
    following_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_follows", "FollowableMetadata")
        verbose_name = _("followable metadata")
        verbose_name_plural = _("followable metadata")

    def __str__(self):
        return f"{self.target} followable metadata"

    @classmethod
    def get_for_object(cls, obj):
        """Return the metadata for the given object, or None if not found."""
        if not obj or not getattr(obj, "pk", None):
            return None
        try:
            ct = ContentType.objects.get_for_model(obj)
            return cls.objects.get(target__content_type=ct, target__object_id=obj.pk)
        except cls.DoesNotExist:
            return None

    @classmethod
    def get_or_create_for_object(cls, obj):
        """Return or create the metadata for the given object."""
        if not obj or not getattr(obj, "pk", None):
            return None
        doc_id = DocumentId.get_or_create_for_object(obj)
        if doc_id:
            metadata, _ = cls.objects.get_or_create(target=doc_id)
            return metadata
        return None

    @classmethod
    def annotate_queryset(cls, queryset):
        """
        Annotate a queryset with followable metadata to prevent N+1 queries when resolving
        `followers_count` / `following_count` for many rows of the same model.
        Adds `_followable_followers_count` and `_followable_following_count` (zero when
        no metadata row exists yet).
        Resolves the model ContentType id once per call (Django's ContentType manager
        caches until `ContentType.objects.clear_cache()`).
        """
        model_cls = queryset.model
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        metadata_qs = cls.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        return queryset.annotate(
            _followable_followers_count=Coalesce(
                Subquery(metadata_qs.values("followers_count")[:1]),
                Value(0),
            ),
            _followable_following_count=Coalesce(
                Subquery(metadata_qs.values("following_count")[:1]),
                Value(0),
            ),
        )


class AbstractFollow(DocumentIdMixin, RelayModel, TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        related_name="follows",
        on_delete=models.SET_NULL,
        null=True,
    )

    actor = models.ForeignKey(
        DocumentId,
        verbose_name=_("actor"),
        related_name="following",
        on_delete=models.CASCADE,
    )

    target_is_following_back = models.BooleanField(default=False)

    target = models.ForeignKey(
        DocumentId,
        verbose_name=_("target"),
        related_name="followers",
        on_delete=models.CASCADE,
    )

    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_follows", "Follow")
        unique_together = [("actor", "target")]

    def __str__(self):
        return "{} followed {}".format(self.actor, self.target)

    def _is_profile_to_profile(self):
        return self.actor.content_type_id == self.target.content_type_id

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)  # Save the instance first

        if created:
            self.update_followers_count(self.target)
            self.update_following_count(self.actor)
            if self._is_profile_to_profile():
                self.update_target_is_following_back()

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
        if self._is_profile_to_profile():
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

    def update_followers_count(self, target_doc_id):
        with transaction.atomic():
            FollowableMetadata = swapper.load_model("baseapp_follows", "FollowableMetadata")
            stats, _ = FollowableMetadata.objects.select_for_update().get_or_create(
                target=target_doc_id
            )
            stats.followers_count = self.__class__.objects.filter(target=target_doc_id).count()
            stats.save(update_fields=["followers_count"])

    def update_following_count(self, actor_doc_id):
        with transaction.atomic():
            FollowableMetadata = swapper.load_model("baseapp_follows", "FollowableMetadata")
            stats, _ = FollowableMetadata.objects.select_for_update().get_or_create(
                target=actor_doc_id
            )
            stats.following_count = self.__class__.objects.filter(actor=actor_doc_id).count()
            stats.save(update_fields=["following_count"])

    @classmethod
    def is_following(cls, actor, target):
        """Check if actor follows target. Both are model instances."""
        actor_ct = ContentType.objects.get_for_model(actor)
        target_ct = ContentType.objects.get_for_model(target)
        return cls.objects.filter(
            actor__content_type=actor_ct,
            actor__object_id=actor.pk,
            target__content_type=target_ct,
            target__object_id=target.pk,
        ).exists()

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import FollowObjectType

        return FollowObjectType
