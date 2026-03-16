import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from graphene_django import DjangoConnectionField

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, get_pk_from_relay_id
from baseapp_core.plugins import apply_if_installed

RateModel = swapper.load_model("baseapp_ratings", "Rate")


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

    def resolve_ratings(self, info, **kwargs):
        if not getattr(self, "is_ratings_enabled", True):
            return RateModel.objects.none()

        if not info.context.user.has_perm("baseapp_ratings.list_ratings"):
            return RateModel.objects.none()

        target_content_type = ContentType.objects.get_for_model(self)
        return RateModel.objects.filter(
            target_content_type=target_content_type,
            target_object_id=self.pk,
        ).order_by("-created")

    def resolve_my_rating(self, info, profile_id=None, **kwargs):
        if not info.context.user.is_authenticated:
            return None

        has_profiles = apps.is_installed("baseapp_profiles")
        if has_profiles:
            return self._resolve_my_rating_with_profiles(info, profile_id=profile_id)
        return self._resolve_my_rating_with_current_user(info)

    def _resolve_my_rating_with_profiles(self, info, profile_id=None):
        Profile = swapper.load_model("baseapp_profiles", "Profile")

        if profile_id:
            pk = get_pk_from_relay_id(profile_id)
            profile = Profile.objects.get_if_member(pk=pk, user=info.context.user)
        else:
            profile = info.context.user.current_profile

        if not profile:
            return None

        return RateModel.objects.filter(
            target_content_type=ContentType.objects.get_for_model(self),
            target_object_id=self.pk,
            user=info.context.user,
            profile=profile,
        ).first()

    def _resolve_my_rating_with_current_user(self, info):
        return RateModel.objects.filter(
            target_content_type=ContentType.objects.get_for_model(self),
            target_object_id=self.pk,
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
    def get_node(self, info, id):
        if not info.context.user.has_perm("baseapp_ratings.view_rate"):
            return None
        return super().get_node(info, id)


class RatingObjectType(
    BaseRatingObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseRatingObjectType.Meta):
        pass
