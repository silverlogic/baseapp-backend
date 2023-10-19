from baseapp_core.graphql import DjangoObjectType
from graphene import relay

from baseapp_notifications.graphql.object_types import NotificationsNode

from ..models import User


class UserNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, NotificationsNode)
        model = User
        fields = ("id",)
