from __future__ import annotations

import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from query_optimizer.compiler import OptimizationCompiler
from query_optimizer.typing import GQLInfo

from baseapp_core.plugins import SharedServiceProvider

Profile = swapper.load_model("baseapp_profiles", "Profile")

# Hint key set by _exclude_blocked_from_foreign_queryset so get_queryset() knows
# filtering was already applied and can skip a redundant .exclude().
_BLOCKED_PROFILES_FILTERED_HINT = "_blocked_profiles_filtered"


class BlockLookupService(SharedServiceProvider):
    @property
    def service_name(self) -> str:
        return "blocks.lookup"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_blocks")

    def exclude_blocked_from_foreign_queryset(
        self, queryset: models.QuerySet, info: GQLInfo
    ) -> models.QuerySet:
        """
        Exclude comments from blocked/blocking profiles.

        Must be called BEFORE evaluate_with_prefetch_hack / optimize
        so that .exclude() cloning doesn't destroy the result cache.
        Sets `_BLOCKED_PROFILES_FILTERED_HINT` on the queryset so
        `get_queryset()` knows filtering was already applied.

        NULLs are filtered out of the id lists before they reach the
        `IN (...)` subqueries: a profile owned by the user that has no blocks
        would otherwise inject a NULL, which makes every row's membership test
        evaluate to UNKNOWN under `exclude()` and be wrongly filtered out.
        """
        if queryset._hints.get(_BLOCKED_PROFILES_FILTERED_HINT):
            return queryset

        user = info.context.user
        if user.is_anonymous:
            queryset._hints[_BLOCKED_PROFILES_FILTERED_HINT] = True
            return queryset

        profile = getattr(user, "current_profile", None)
        if profile:
            blocked_profile_ids = profile.blocking.filter(target_id__isnull=False).values_list(
                "target_id", flat=True
            )
            blocker_profile_ids = profile.blockers.filter(actor_id__isnull=False).values_list(
                "actor_id", flat=True
            )
        else:
            # Fallback for contexts where middleware did not set current_profile:
            # apply the union of block relations for all profiles owned by the user.
            owned_profiles = Profile.objects.filter(owner=user)
            blocked_profile_ids = owned_profiles.filter(
                blocking__target_id__isnull=False
            ).values_list("blocking__target_id", flat=True)
            blocker_profile_ids = owned_profiles.filter(
                blockers__actor_id__isnull=False
            ).values_list("blockers__actor_id", flat=True)

        qs = queryset.exclude(
            Q(profile__id__in=blocked_profile_ids) | Q(profile__id__in=blocker_profile_ids)
        )
        qs._hints[_BLOCKED_PROFILES_FILTERED_HINT] = True
        return qs

    def has_block_between(self, profile_ids_a, profile_ids_b) -> bool:
        """Return True if any block exists between the two profile-id sets, in
        either direction (a profile in A blocks one in B, or vice versa).

        Lets other packages gate actions on blocks (e.g. chat creation /
        messaging) without importing the Block model. Either argument may be a
        list or a queryset of profile ids.
        """
        Block = swapper.load_model("baseapp_blocks", "Block")
        return Block.objects.filter(
            Q(actor_id__in=profile_ids_a, target_id__in=profile_ids_b)
            | Q(actor_id__in=profile_ids_b, target_id__in=profile_ids_a)
        ).exists()

    def get_blocked_profile_ids(self, profile_id) -> models.QuerySet:
        """Return a queryset of profile ids that `profile_id` blocks.

        NULL targets are excluded so the result is safe to use inside an
        `exclude(... __in=...)` subquery (a NULL would otherwise make the
        membership test UNKNOWN and drop unrelated rows).
        """
        Block = swapper.load_model("baseapp_blocks", "Block")
        return Block.objects.filter(actor_id=profile_id, target_id__isnull=False).values_list(
            "target_id", flat=True
        )

    def get_blocker_profile_ids(self, profile_id) -> models.QuerySet:
        """Return a queryset of profile ids that block `profile_id` (NULL-safe,
        see :meth:`get_blocked_profile_ids`)."""
        Block = swapper.load_model("baseapp_blocks", "Block")
        return Block.objects.filter(target_id=profile_id, actor_id__isnull=False).values_list(
            "actor_id", flat=True
        )


class BlockableMetadataService(SharedServiceProvider):
    """
    Service that provides blockable metadata (blockers / blocking counts) for
    any object that has a `DocumentId`. Registered in `apps.py` via
    `register_shared_services`.
    """

    @property
    def service_name(self) -> str:
        return "blockable_metadata"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_blocks")

    def _get_model(self) -> type[models.Model]:
        return swapper.load_model("baseapp_blocks", "BlockableMetadata")

    def get_metadata(self, obj) -> models.Model | None:
        """Return `BlockableMetadata` for `obj`, or `None` if not found."""
        return self._get_model().get_for_object(obj)

    def get_or_create_metadata(self, obj) -> models.Model | None:
        """Return or create `BlockableMetadata` for `obj`."""
        return self._get_model().get_or_create_for_object(obj)

    def get_blockers_count(self, obj) -> int:
        """Return number of blocks where `obj` is the target. Uses annotation if available."""
        if hasattr(obj, "_blockable_blockers_count"):
            val = obj._blockable_blockers_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.blockers_count if metadata else 0

    def get_blocking_count(self, obj) -> int:
        """Return number of blocks where `obj` is the actor. Uses annotation if available."""
        if hasattr(obj, "_blockable_blocking_count"):
            val = obj._blockable_blocking_count
            return val if val is not None else 0
        metadata = self.get_metadata(obj)
        return metadata.blocking_count if metadata else 0

    def recompute_blockers_count(self, target) -> None:
        """Recount blocks where `target` is the target and write through to the metadata row."""
        if not target or not getattr(target, "pk", None):
            return
        metadata = self.get_or_create_metadata(target)
        if metadata is None:
            return
        # `blockers` is the reverse manager from `AbstractBlock.target` (Profile FK).
        count = target.blockers.count() if hasattr(target, "blockers") else 0
        if metadata.blockers_count != count:
            metadata.blockers_count = count
            metadata.save(update_fields=["blockers_count", "modified"])

    def recompute_blocking_count(self, actor) -> None:
        """Recount blocks where `actor` is the actor and write through to the metadata row."""
        if not actor or not getattr(actor, "pk", None):
            return
        metadata = self.get_or_create_metadata(actor)
        if metadata is None:
            return
        count = actor.blocking.count() if hasattr(actor, "blocking") else 0
        if metadata.blocking_count != count:
            metadata.blocking_count = count
            metadata.save(update_fields=["blocking_count", "modified"])

    def annotate_queryset(self, queryset) -> models.QuerySet:
        """Bulk-annotate `queryset` with both counts. Useful for non-GraphQL
        callers (admin, DRF, management commands). The GraphQL path attaches
        each annotation on-demand via the field-level optimizer hooks below."""
        return self._get_model().annotate_queryset(queryset)

    # --- Correlated subquery builders, used by both `annotate_queryset` on the
    #     metadata model and the optimizer-compiler hooks below. -------------

    def _blockers_count_subquery(self, model_cls) -> Coalesce:
        """Correlated subquery producing `blockers_count` for a row of `model_cls`."""
        BlockableMetadata = self._get_model()
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        qs = BlockableMetadata.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        return Coalesce(
            Subquery(
                qs.values("blockers_count")[:1],
                output_field=models.PositiveIntegerField(),
            ),
            Value(0),
        )

    def _blocking_count_subquery(self, model_cls) -> Coalesce:
        """Correlated subquery producing `blocking_count` for a row of `model_cls`."""
        BlockableMetadata = self._get_model()
        ct_id = ContentType.objects.get_for_model(model_cls).pk
        qs = BlockableMetadata.objects.filter(
            target__content_type_id=ct_id,
            target__object_id=OuterRef("pk"),
        )
        return Coalesce(
            Subquery(
                qs.values("blocking_count")[:1],
                output_field=models.PositiveIntegerField(),
            ),
            Value(0),
        )

    def annotate_blockers_count_in_optimizer_compiler(self, compiler: OptimizationCompiler) -> None:
        """Attach `_blockable_blockers_count` to the parent optimizer's annotations.

        Wired from `BlocksInterface.blockers_count.optimizer_hook` so the
        subquery only fires when the GraphQL query actually selects
        `blockersCount`. Setting the annotation on `optimizer.annotations` also
        triggers `query_optimizer`'s auto-promotion of `select_related` to
        `prefetch_related` for nested FK paths (e.g. `block.target`), which is
        what carries the annotation through to the nested Profile load.
        """
        parent = compiler.optimizer
        if parent is None or parent.model is None:
            return
        parent.annotations.setdefault(
            "_blockable_blockers_count", self._blockers_count_subquery(parent.model)
        )

    def annotate_blocking_count_in_optimizer_compiler(self, compiler: OptimizationCompiler) -> None:
        """Attach `_blockable_blocking_count` to the parent optimizer's annotations.

        Wired from `BlocksInterface.blocking_count.optimizer_hook` — same mechanism
        as `annotate_blockers_count_in_optimizer_compiler`."""
        parent = compiler.optimizer
        if parent is None or parent.model is None:
            return
        parent.annotations.setdefault(
            "_blockable_blocking_count", self._blocking_count_subquery(parent.model)
        )
