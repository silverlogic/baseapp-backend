import django_filters
import graphene
import swapper
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.db.models import Prefetch, QuerySet
from query_optimizer.compiler import OptimizationCompiler

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import resolve_document_content_object
from baseapp_core.models import DocumentId
from baseapp_core.plugins import shared_services

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class FollowsFilter(django_filters.FilterSet):
    class Meta:
        model = Follow
        fields = ["target_is_following_back"]


class BaseFollowObjectType:
    actor_object = graphene.Field(RelayNode)
    target_object = graphene.Field(RelayNode)

    class Meta:
        model = Follow
        fields = (
            "id",
            "user",
            "actor",
            "target",
            "target_is_following_back",
            "created",
            "modified",
        )
        interfaces = (RelayNode,)
        filterset_class = FollowsFilter

    def resolve_actor_object(self, info: graphene.ResolveInfo) -> object:
        return resolve_document_content_object(self.actor, info)

    def resolve_target_object(self, info: graphene.ResolveInfo) -> object:
        return resolve_document_content_object(self.target, info)

    @classmethod
    def pre_optimization_hook(cls, queryset: QuerySet, optimizer: OptimizationCompiler) -> QuerySet:
        queryset = super().pre_optimization_hook(queryset, optimizer)

        # Prefetch the actor / target DocumentId rows AND the GFK-pointed
        # `content_object` in a single batch per content type. Without this,
        # `self.actor.content_object` (used by `resolve_actor_object`) fires one
        # DocumentId + one Profile fetch per follow row. `GenericPrefetch`
        # (Django 5.0+) lets us declare which model querysets to use per content type —
        # Profile is by far the most common, so we warm that one. Other content types
        # still fall back to the per-row request cache in `_resolve_document_object`.
        #
        # The prefetched Profile queryset is also annotated so the nested
        # `actorObject { id followersCount followingCount }` resolvers don't N+1:
        #   • `mapped_public_id` — relay id (same trick the recursive walker in
        #     `DjangoObjectType.pre_optimization_hook` does for the top-level
        #     Follow rows).
        #   • `_followable_followers_count` / `_followable_following_count` — pulled
        #     from FollowableMetadata via subquery so `FollowsInterface.resolve_*_count`
        #     reads off the instance instead of refetching per row.
        from baseapp_core.hashids.strategies import (
            get_hashids_strategy_from_instance_or_cls,
        )

        profile_strategy = get_hashids_strategy_from_instance_or_cls(Profile)
        profile_qs = Profile.objects.annotate(
            **profile_strategy.queryset_annotator.get_annotations(Profile)
        )
        if service := shared_services.get("followable_metadata"):
            profile_qs = service.annotate_queryset(profile_qs)
        prefetched_object_querysets = [profile_qs]
        document_qs = DocumentId.objects.select_related("content_type").prefetch_related(
            GenericPrefetch("content_object", prefetched_object_querysets),
        )
        queryset = queryset.prefetch_related(
            Prefetch("actor", queryset=document_qs),
            Prefetch("target", queryset=document_qs),
        )

        # The interface declares fields the optimizer doesn't see at compile time
        # (actor_object / target_object route through DocumentId). Make sure the FK
        # columns are not stripped by only_fields.
        for required in ("id", "actor_id", "target_id"):
            if required not in optimizer.only_fields:
                optimizer.only_fields.append(required)
        return queryset


class FollowObjectType(BaseFollowObjectType, DjangoObjectType):
    class Meta(BaseFollowObjectType.Meta):
        pass
