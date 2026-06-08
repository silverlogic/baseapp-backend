import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import F, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentId, DocumentIdMixin, DocumentIdUniqueTargetMixin


class AbstractFollowableMetadata(DocumentIdUniqueTargetMixin, TimeStampedModel):
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
            self._adjust_followable_metadata(self.target_id, "followers_count", 1)
            self._adjust_followable_metadata(self.actor_id, "following_count", 1)
            if self._is_profile_to_profile():
                self._sync_target_is_following_back_on_create()

    def delete(self, *args, **kwargs):
        actor_id = self.actor_id
        target_id = self.target_id
        # Resolve _is_profile_to_profile() while the FK descriptor cache is still warm —
        # accessing self.actor / self.target after super().delete() would trigger a
        # fresh fetch on a row whose FK referent could in principle be gone.
        is_p2p = self._is_profile_to_profile()
        super().delete(*args, **kwargs)

        self._adjust_followable_metadata(target_id, "followers_count", -1)
        self._adjust_followable_metadata(actor_id, "following_count", -1)
        if is_p2p:
            self._clear_reciprocal_target_is_following_back(actor_id, target_id)

    @classmethod
    def _adjust_followable_metadata(cls, doc_id, field, delta):
        """
        Atomically increment / decrement a `FollowableMetadata` counter via
        `F` expression. Live path — keeps follow / unfollow O(1) per write,
        regardless of how many follows the target / actor already has.

        Use `recount_followers_count` / `recount_following_count` for periodic
        reconciliation that re-derives the counter from the live row count; that
        path SELECT FOR UPDATEs and runs a full COUNT(*), so it serializes writers
        on hot rows and must NOT be on the live save / delete path.
        """
        FollowableMetadata = swapper.load_model("baseapp_follows", "FollowableMetadata")
        affected = FollowableMetadata.objects.filter(target_id=doc_id).update(
            **{field: F(field) + delta}
        )
        if affected == 0 and delta > 0:
            # First adjustment for this target / actor — seed the row at the right
            # starting count. `update_or_create` is idempotent under concurrent
            # writers thanks to the unique target_id constraint.
            FollowableMetadata.objects.update_or_create(target_id=doc_id, defaults={field: delta})

    def _sync_target_is_following_back_on_create(self):
        """
        When a Follow is created and a reciprocal Follow already exists, flip
        `target_is_following_back` on BOTH rows via single-row UPDATEs instead of
        re-entering `save()` — the previous implementation called
        `self.save(update_fields=[...])` which is fragile (the second save triggers
        the post-create branch again, and only avoided infinite recursion because
        `created` was False the second time around).
        """
        cls = self.__class__
        reciprocal_exists = cls.objects.filter(
            actor_id=self.target_id,
            target_id=self.actor_id,
        ).exists()
        if not reciprocal_exists:
            return
        cls.objects.filter(pk=self.pk).update(target_is_following_back=True)
        cls.objects.filter(
            actor_id=self.target_id,
            target_id=self.actor_id,
        ).update(target_is_following_back=True)
        # In-memory consistency for callers who hold this instance.
        self.target_is_following_back = True

    @classmethod
    def _clear_reciprocal_target_is_following_back(cls, actor_id, target_id):
        """
        When a Follow is deleted, flip `target_is_following_back` on the
        reciprocal Follow (if any) back to False via a single UPDATE — same
        no-recursive-save reasoning as the create path.
        """
        cls.objects.filter(
            actor_id=target_id,
            target_id=actor_id,
        ).update(target_is_following_back=False)

    @classmethod
    def recount_followers_count(cls, target):
        """
        Periodic-reconciliation helper: recompute `followers_count` from the
        live follow rows under a row lock. Use this from a Celery beat task, NOT
        from the live save / delete path (the live path uses
        :meth:`_adjust_followable_metadata`, which is O(1) and lock-free).
        """
        cls._recount(target, "followers_count", "target_id")

    @classmethod
    def recount_following_count(cls, actor):
        cls._recount(actor, "following_count", "actor_id")

    @classmethod
    def _recount(cls, doc_or_id, metadata_field, follow_field):
        doc_id = doc_or_id.pk if hasattr(doc_or_id, "pk") else doc_or_id
        FollowableMetadata = swapper.load_model("baseapp_follows", "FollowableMetadata")
        with transaction.atomic():
            stats, _ = FollowableMetadata.objects.select_for_update().get_or_create(
                target_id=doc_id
            )
            count = cls.objects.filter(**{follow_field: doc_id}).count()
            setattr(stats, metadata_field, count)
            stats.save(update_fields=[metadata_field])

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
