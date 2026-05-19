from typing import Iterable, List, Optional

import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce
from query_optimizer.compiler import OptimizationCompiler
from query_optimizer.optimizer import QueryOptimizer

from baseapp_core.graphql.utils import get_pk_from_relay_id
from baseapp_core.models import DocumentId
from baseapp_core.plugins import SharedServiceProvider

from .signals import mentions_changed

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
    ):
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

            existing = set(Mention.objects.filter(target=doc).values_list("profile_id", flat=True))
            to_remove = existing - new_pks
            to_add = new_pks - existing

            if to_remove:
                Mention.objects.filter(target=doc, profile_id__in=to_remove).delete()
            if to_add:
                Mention.objects.bulk_create(
                    [Mention(target=doc, profile_id=pk) for pk in to_add],
                    ignore_conflicts=True,
                )

            if to_add or to_remove:
                mentions_changed.send(
                    sender=Mention,
                    target=target_obj,
                    added=list(to_add),
                    removed=list(to_remove),
                )

        return list(Mention.objects.filter(target=doc).select_related("profile"))

    def resolve_mentioned_profiles(
        self,
        mentioned_profile_ids: Iterable[str],
        exclude_profile: Optional["Profile"] = None,
    ) -> List["Profile"]:
        """Resolve Relay global IDs to Profile instances, filtering out self-mention.

        Silently drops malformed or stale IDs so a flaky client reference does not
        break the parent mutation.
        """
        pks: List[int] = []
        for relay_id in mentioned_profile_ids or []:
            try:
                pk = get_pk_from_relay_id(relay_id)
            except Exception:  # noqa: BLE001 — malformed IDs are dropped intentionally
                continue
            if pk is None:
                continue
            # `get_pk_from_relay_id` returns whatever survived hashids/base64 decoding —
            # for some malformed inputs that's an empty string or a non-numeric chunk
            # rather than a raised exception. Coerce to int explicitly so a stray value
            # never reaches the queryset filter (where it would blow up the parent mutation).
            try:
                pks.append(int(pk))
            except (TypeError, ValueError):
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

    def _mention_model(self):
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
        return self._mention_model().objects.filter(target=doc).count()

    def _mentions_count_subquery(self, model_cls):
        """Correlated subquery that produces the mentions count for a row of `model_cls`."""
        Mention = self._mention_model()
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        count_qs = (
            Mention.objects.filter(
                target__content_type_id=ct_id,
                target__object_id=OuterRef("pk"),
            )
            .order_by()
            .values("target")
            .annotate(c=Count("id"))
            .values("c")
        )
        return Coalesce(Subquery(count_qs[:1]), Value(0))

    def _target_doc_id_subquery(self, model_cls):
        """Correlated subquery that produces the DocumentId pk for a row of `model_cls`."""
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        doc_qs = DocumentId.objects.filter(
            content_type_id=ct_id,
            object_id=OuterRef("pk"),
        )
        return Subquery(doc_qs.values("id")[:1])

    def annotate_queryset(self, queryset):
        """Annotate `queryset` with `_mentions_count` + `_mention_target_doc_id`.

        Both annotations key off the consuming model's `(content_type, pk)` so
        the same hook works for any DocumentId-aware model (Comment, Message,
        ContentPost, ...). Used by non-GraphQL callers (DRF views, admin,
        management commands); the GraphQL path attaches each annotation
        on-demand via the field-level optimizer hooks below.
        """
        return queryset.annotate(
            _mention_target_doc_id=self._target_doc_id_subquery(queryset.model),
            _mentions_count=self._mentions_count_subquery(queryset.model),
        )

    def annotate_mentions_count_in_optimizer_compiler(self, compiler: OptimizationCompiler):
        """Attach `_mentions_count` to the parent optimizer's annotations.

        Wired from `MentionsInterface.mentions_count.optimizer_hook` so the
        subquery only fires when the GraphQL query actually selects
        `mentionsCount` — no wasted SQL on queries that ignore the field.
        """
        parent = compiler.optimizer
        if parent is None or parent.model is None:
            return
        parent.annotations.setdefault(
            "_mentions_count", self._mentions_count_subquery(parent.model)
        )

    def annotate_target_doc_id_in_optimizer_compiler(self, compiler: OptimizationCompiler):
        """Attach `_mention_target_doc_id` to the parent optimizer's annotations.

        Wired from `MentionsInterface.is_mentioning_profile.optimizer_hook` so
        the per-row `Mention.objects.filter(target_id=…, profile_id=…).exists()`
        in the resolver can read the doc pk off the row instead of issuing a
        `DocumentId.get_or_create_for_object` per parent. `setdefault` so
        sibling hooks that need the same annotation don't overwrite it.
        """
        parent = compiler.optimizer
        if parent is None or parent.model is None:
            return
        parent.annotations.setdefault(
            "_mention_target_doc_id", self._target_doc_id_subquery(parent.model)
        )

    def prefetch_mentions_in_optimizer_compiler(self, compiler: OptimizationCompiler):
        """
        Walks the parent optimizer through document__mentions.

        The mentions connection is a "virtual relation" on the consuming
        model — there's no direct FK or M2M from the consumer to Mention;
        the link runs through DocumentId (consumer → document via
        GenericRelation → mentions reverse-FK on the through-table).
        Without a hint, the optimizer treats the field as opaque and falls back
        to a per-parent fetch, producing an N+1.

        Registering a child QueryOptimizer keyed on document__mentions
        promotes the field to a regular Django prefetch_related: one batched
        SELECT for the parents' DocumentId rows, one batched SELECT for the
        mentions, joined to Profile via select_related. The resolver
        below reads the cached queryset off root.document.
        """

        parent_optimizer = compiler.optimizer
        if parent_optimizer is None or parent_optimizer.model is None:
            return

        if "document__mentions" in parent_optimizer.prefetch_related:
            return

        Mention = swapper.load_model("baseapp_mentions", "Mention")

        mentions_opt = QueryOptimizer(
            model=Mention,
            info=compiler.info,
            name="document__mentions",
            parent=parent_optimizer,
        )

        # `recursive_set_annotations` in `BaseAppDjangoObjectType.pre_optimization_hook`
        # gates annotation attachment on `"id" in only_fields`; without this, the
        # Profile prefetch below would NOT receive its `mapped_public_id` annotation
        # and the relay-id resolver would fall back to a per-row `DocumentId` lookup.
        mentions_opt.only_fields.append("id")
        mentions_opt.related_fields.extend(["target_id", "profile_id"])

        profile_opt = QueryOptimizer(
            model=Profile,
            info=compiler.info,
            name="profile",
            parent=mentions_opt,
        )
        # Same gate: "id" in only_fields ⇒ Profile gets its `mapped_public_id`
        # subquery annotated, killing the per-row DocumentId lookup on relay-id.
        profile_opt.only_fields.append("id")
        # With annotations attached, the optimizer promotes this from
        # `select_related` to `prefetch_related` (so we get one batched Profile
        # SELECT instead of N inline joins). Either path works for query count;
        # the promotion happens automatically inside `QueryOptimizer.process`.
        mentions_opt.select_related["profile"] = profile_opt

        parent_optimizer.prefetch_related["document__mentions"] = mentions_opt
