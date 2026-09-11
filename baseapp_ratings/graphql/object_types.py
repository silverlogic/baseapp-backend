from typing import TYPE_CHECKING, Optional

import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from query_optimizer import DjangoConnectionField

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id
from baseapp_core.plugins import apply_if_installed, shared_services

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet

    from ..services import RatableMetadataService

RateModel = swapper.load_model("baseapp_ratings", "Rate")


def _service() -> "RatableMetadataService | None":
    return shared_services.get("ratable_metadata")


class RatingsInterface(RelayNode):
    ratings_count = graphene.Int()
    ratings_sum = graphene.Int()
    ratings_average = graphene.Float()
    ratings = DjangoConnectionField(get_object_type_for_model(RateModel))
    is_ratings_enabled = graphene.Boolean(required=True)
    my_rating = graphene.Field(
        get_object_type_for_model(RateModel),
        required=False,
        **apply_if_installed("baseapp_profiles", {"profile_id": graphene.ID(required=False)}),
    )

    def resolve_ratings_count(self, info) -> int:
        if service := _service():
            return service.get_ratings_count(self)
        return 0

    def resolve_ratings_sum(self, info) -> int:
        if service := _service():
            return service.get_ratings_sum(self)
        return 0

    def resolve_ratings_average(self, info) -> float:
        if service := _service():
            return service.get_ratings_average(self)
        return 0.0

    def resolve_is_ratings_enabled(self, info) -> bool:
        if service := _service():
            return service.is_ratings_enabled(self)
        return True

    def resolve_ratings(self, info, **kwargs) -> "QuerySet":
        service = _service()
        if service is not None and not service.is_ratings_enabled(self):
            return RateModel.objects.none()

        if not info.context.user.has_perm("baseapp_ratings.list_ratings"):
            return RateModel.objects.none()

        target_content_type = ContentType.objects.get_for_model(self)
        return RateModel.objects.filter(
            target_document__content_type=target_content_type,
            target_document__object_id=self.pk,
        ).order_by("-created")

    def resolve_my_rating(self, info, profile_id=None, **kwargs) -> "Model | None":
        if not info.context.user.is_authenticated:
            return None

        has_profiles = apps.is_installed("baseapp_profiles")
        if has_profiles:
            return RatingsInterface._resolve_my_rating_with_profiles(
                self, info, profile_id=profile_id
            )
        return RatingsInterface._resolve_my_rating_with_current_user(self, info)

    @staticmethod
    def _resolve_my_rating_with_profiles(root, info, profile_id=None) -> "Model | None":
        Profile = swapper.load_model("baseapp_profiles", "Profile")

        if profile_id:
            pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=pk, user=info.context.user)
        else:
            profile = info.context.user.current_profile

        if not profile:
            return None

        return RateModel.objects.filter(
            target_document__content_type=ContentType.objects.get_for_model(root),
            target_document__object_id=root.pk,
            user=info.context.user,
            profile=profile,
        ).first()

    @staticmethod
    def _resolve_my_rating_with_current_user(root, info) -> "Model | None":
        return RateModel.objects.filter(
            target_document__content_type=ContentType.objects.get_for_model(root),
            target_document__object_id=root.pk,
            user=info.context.user,
        ).first()


class BaseRatingObjectType:
    target = graphene.Field(RelayNode)

    class Meta:
        interfaces = (RelayNode,)
        model = RateModel
        fields = (
            "id",
            "user",
            *apply_if_installed("baseapp_profiles", ["profile"]),
            "created",
            "modified",
            "target",
            "value",
        )

    @classmethod
    def get_node(cls, info: graphene.ResolveInfo, id: str) -> Optional["BaseRatingObjectType"]:
        if not info.context.user.has_perm("baseapp_ratings.view_rate"):
            return None
        return super().get_node(info, id)


class RatingObjectType(
    BaseRatingObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseRatingObjectType.Meta):
        pass
