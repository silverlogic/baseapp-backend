from baseapp_core.graphql import DjangoObjectType
from graphene import relay

from baseapp_notifications.graphql.object_types import NotificationsInterface

from ..models import User


class UserNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, NotificationsInterface)
        model = User
        fields = ("id",)
