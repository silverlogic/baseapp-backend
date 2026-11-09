from typing import TYPE_CHECKING, Iterable, List, Optional

import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from baseapp_core.graphql.utils import get_pk_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.plugins import SharedServiceProvider

from .signals import mentions_changed

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from .models import AbstractBaseMention

Profile = swapper.load_model("baseapp_profiles", "Profile")


class MentionsService(SharedServiceProvider):
    """Shared service exposing `update_mentions` for cross-package consumers.

    Consumer mutations (comments, chats, content_feed, ...) call
    `shared_services.get("mentions").update_mentions(...)` so the
    dependency stays one-way.
    """

    @property
    def service_name(self) -> str:
        return "mentions"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_mentions")

    def update_mentions(
        self,
        target_obj,
        mentioned_profile_ids: Iterable[str],
        exclude_profile: Optional["Profile"] = None,
    ) -> "list[AbstractBaseMention]":
        """Replace the Mention rows for `target_obj` with the resolved profile set.

        Mirrors `m2m.set(...)` semantics: inserts new, deletes removed, leaves
        unchanged rows untouched. Single public extension point for consumer
        mutations. Fires `mentions_changed` once per call (batched) with the
        delta lists.

        Concurrent callers writing the same target are serialized via a
        `select_for_update` lock on the target's `DocumentId` row, so the
        "replace" semantics survive overlapping requests instead of merging the
        two callers' deltas against the same stale `existing` snapshot.
        """
        Mention = swapper.load_model("baseapp_mentions", "Mention")

        profiles = self.resolve_mentioned_profiles(
            mentioned_profile_ids, exclude_profile=exclude_profile
        )
        new_pks = {p.pk for p in profiles}
        doc = DocumentId.get_or_create_for_object(target_obj)

        with transaction.atomic():
            DocumentId.objects.select_for_update().filter(pk=doc.pk).first()

            existing = set(
                Mention.objects.filter(target_document=doc).values_list("profile_id", flat=True)
            )
            to_remove = existing - new_pks
            to_add = new_pks - existing

            if to_remove:
                Mention.objects.filter(target_document=doc, profile_id__in=to_remove).delete()
            if to_add:
                Mention.objects.bulk_create(
                    [Mention(target_document=doc, profile_id=pk) for pk in to_add],
                    ignore_conflicts=True,
                )

            if to_add or to_remove:
                transaction.on_commit(
                    lambda: mentions_changed.send(
                        sender=Mention,
                        target=target_obj,
                        added=list(to_add),
                        removed=list(to_remove),
                    )
                )

        return list(Mention.objects.filter(target_document=doc).select_related("profile"))

    def resolve_mentioned_profiles(
        self,
        mentioned_profile_ids: Iterable[str],
        exclude_profile: Optional["Profile"] = None,
    ) -> List["Profile"]:
        """Resolve Relay global IDs to Profile instances, filtering out self-mention.

        Silently drops malformed or stale IDs so a flaky client reference does not
        break the parent mutation.
        """
        pks: List = []
        for relay_id in mentioned_profile_ids or []:
            try:
                pk = get_pk_from_relay_id(relay_id)
            except Exception:  # noqa: BLE001 — malformed IDs are dropped intentionally
                continue
            if pk is None:
                continue
            # `get_pk_from_relay_id` returns whatever survived hashids/base64 decoding —
            # for some malformed inputs that's an empty string or a non-numeric chunk
            # rather than a raised exception. Normalize through the swapped Profile's
            # own PK field so a stray value never reaches the queryset filter, and
            # so projects that swap Profile to a non-integer PK (UUID, string) still
            # resolve real relay IDs instead of having them coerced away.
            try:
                pks.append(Profile._meta.pk.to_python(pk))
            except (TypeError, ValueError, ValidationError):
                continue

        if not pks:
            return []

        queryset = Profile.objects.filter(pk__in=pks)
        if exclude_profile is not None and exclude_profile.pk is not None:
            queryset = queryset.exclude(pk=exclude_profile.pk)
        return list(queryset)


class MentionableMetadataService(SharedServiceProvider):
    """Annotation-based metadata service for `MentionsInterface` resolvers.

    Unlike `FollowableMetadataService` (which reads from a denormalized
    `FollowableMetadata` row), mentions are cheap to count off the through-table
    directly, so this service computes counts via correlated subqueries and
    threads them onto the consuming object's queryset as `_mentions_count`
    plus a pre-resolved `_mention_target_doc_id`. With both annotated, the
    resolvers in `MentionsInterface` skip a per-row `DocumentId.get_or_create_for_object`
    and a per-row `count()`.
    """

    @property
    def service_name(self) -> str:
        return "mentionable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_mentions")

    def _mention_model(self) -> "type[AbstractBaseMention]":
        return swapper.load_model("baseapp_mentions", "Mention")

    def get_mentions_count(self, obj) -> int:
        """Return mentions count for `obj`. Uses annotation if available."""
        if hasattr(obj, "_mentions_count"):
            val = obj._mentions_count
            return val if val is not None else 0

        # Fallback for unannotated calls
        doc = DocumentId.get_or_create_for_object(obj)
        if doc is None:
            return 0
        return self._mention_model().objects.filter(target_document=doc).count()

    def _mentions_count_subquery(self, model_cls) -> Coalesce:
        """Correlated subquery that produces the mentions count for a row of `model_cls`."""
        Mention = self._mention_model()
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        count_qs = (
            Mention.objects.filter(
                target_document__content_type_id=ct_id,
                target_document__object_id=OuterRef("pk"),
            )
            .order_by()
            .values("target_document")
            .annotate(c=Count("id"))
            .values("c")
        )
        return Coalesce(Subquery(count_qs[:1]), Value(0))

    def _target_doc_id_subquery(self, model_cls) -> Subquery:
        """Correlated subquery that produces the DocumentId pk for a row of `model_cls`."""
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        doc_qs = DocumentId.objects.filter(
            content_type_id=ct_id,
            object_id=OuterRef("pk"),
        )
        return Subquery(doc_qs.values("id")[:1])

    def annotate_queryset(self, queryset) -> "QuerySet":
        """Annotate `queryset` with `_mentions_count` + `_mention_target_doc_id`.

        Both annotations key off the consuming model's `(content_type, pk)` so
        the same hook works for any DocumentId-aware model (Comment, Message,
        ContentPost, ...). Used by non-GraphQL callers (DRF views, admin,
        management commands); the GraphQL path attaches each annotation
        on-demand via the `MentionsInterface` field optimizer hints.
        """
        return queryset.annotate(
            _mention_target_doc_id=self._target_doc_id_subquery(queryset.model),
            _mentions_count=self._mentions_count_subquery(queryset.model),
        )
