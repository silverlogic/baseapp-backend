import django_filters
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
    class Meta:
        model = Follow
        fields = "__all__"
        interfaces = (RelayNode,)
        filterset_class = FollowsFilter


class FollowObjectType(
    BaseFollowObjectType, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseFollowObjectType.Meta):
        pass
