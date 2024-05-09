import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from baseapp_core.graphql import DjangoObjectType

from django.contrib.contenttypes.models import ContentType
from graphene import relay
from graphene_django import DjangoConnectionField

RateModel = swapper.load_model("baseapp_ratings", "Rate")


class RatingsInterface(relay.Node):
    ratings_count = graphene.Int()
    ratings_sum = graphene.Int()
    ratings_average = graphene.Float()
    ratings = DjangoConnectionField(lambda: RatingObjectType)
    is_ratings_enabled = graphene.Boolean(required=True)
    my_rating = graphene.Field(lambda: RatingObjectType, required=False)

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

    def resolve_my_rating(self, info, **kwargs):
        if info.context.user.is_authenticated:
            target_content_type = ContentType.objects.get_for_model(self)
            return RateModel.objects.filter(
                target_content_type=target_content_type,
                target_object_id=self.pk,
                user=info.context.user,
            ).first()


class RatingObjectType(gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType):
    target = graphene.Field(relay.Node)

    class Meta:
        interfaces = (relay.Node,)
        model = RateModel
        fields = (
            "id",
            "user",
            "created",
            "modified",
            "target",
            "value",
        )

    @classmethod
    def get_node(self, info, id):
        if not info.context.user.has_perm("baseapp_ratings.view_rate"):
            return None
        node = super().get_node(info, id)
        return node
