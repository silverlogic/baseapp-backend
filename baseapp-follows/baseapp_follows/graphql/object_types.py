import django_filters
import graphene_django_optimizer as gql_optimizer
import swapper
from baseapp_core.graphql import DjangoObjectType
from graphene import relay

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")


class FollowsFilter(django_filters.FilterSet):
    class Meta:
        model = Follow
        fields = ["target_is_following_back"]


class FollowObjectType(gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType):
    class Meta:
        model = Follow
        fields = "__all__"
        interfaces = (relay.Node,)
        filterset_class = FollowsFilter
