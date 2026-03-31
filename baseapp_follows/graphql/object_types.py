import django_filters
import graphene
import graphene_django_optimizer as gql_optimizer
import swapper

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode

Follow = swapper.load_model("baseapp_follows", "Follow")


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

    def resolve_actor_object(self, info):
        return self.actor.content_object

    def resolve_target_object(self, info):
        return self.target.content_object


class FollowObjectType(
    BaseFollowObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseFollowObjectType.Meta):
        pass
