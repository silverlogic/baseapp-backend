from baseapp_core.graphql import DjangoObjectType
from graphene import relay

from baseapp_follows.graphql.object_types import FollowsInterface

from ..models import User


class UserNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, FollowsInterface)
        model = User
        fields = ("id",)
