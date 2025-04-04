import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.contrib.contenttypes.models import ContentType
from graphene import relay
from graphene_django import DjangoConnectionField

from baseapp_core.graphql import (
    DjangoObjectType,
    get_object_type_for_model,
    get_pk_from_relay_id,
)

RateModel = swapper.load_model("baseapp_ratings", "Rate")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class RatingsInterface(relay.Node):
    ratings_count = graphene.Int()
    ratings_sum = graphene.Int()
    ratings_average = graphene.Float()
    ratings = DjangoConnectionField(get_object_type_for_model(RateModel))
    is_ratings_enabled = graphene.Boolean(required=True)
    my_rating = graphene.Field(
        get_object_type_for_model(RateModel),
        required=False,
        profile_id=graphene.ID(required=False),
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

    def resolve_my_rating(self, info, profile_id, **kwargs):
        if info.context.user.is_authenticated:
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
                profile=info.context.user.current_profile,
            ).first()


class BaseRatingObjectType:
    target = graphene.Field(relay.Node)

    class Meta:
        interfaces = (relay.Node,)
        model = RateModel
        fields = (
            "id",
            "user",
            "profile",
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
