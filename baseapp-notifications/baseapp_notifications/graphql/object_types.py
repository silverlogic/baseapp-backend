import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from baseapp_core.graphql import DjangoObjectType
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

from .filters import NotificationFilter

Notification = swapper.load_model("notifications", "Notification")


class NotificationsNode(relay.Node):
    notifications_unread_count = graphene.Int()
    notifications = DjangoFilterConnectionField(
        lambda: NotificationNode, filterset_class=NotificationFilter
    )

    def resolve_notifications_unread_count(self, info):
        if self.is_authenticated:
            return Notification.objects.filter(recipient=self, unread=True).count()
        return 0

    def resolve_notifications(self, info, **kwargs):
        if info.context.user.is_authenticated and info.context.user == self:
            return Notification.objects.filter(recipient=info.context.user).order_by(
                "-unread", "-timestamp"
            )
        return Notification.objects.none()


class NotificationNode(DjangoObjectType):
    actor = graphene.Field(relay.Node)
    target = graphene.Field(relay.Node)
    action_object = graphene.Field(relay.Node)

    class Meta:
        interfaces = (relay.Node,)
        model = Notification

    @classmethod
    def get_node(cls, info, id):
        if not info.context.user.is_authenticated:
            return None

        try:
            queryset = cls.get_queryset(cls._meta.model.objects, info)
            return queryset.get(id=id, recipient=info.context.user)
        except cls._meta.model.DoesNotExist:
            return None

    @classmethod
    def get_queryset(cls, queryset, info):
        if not info.context.user.is_authenticated:
            return queryset.none()

        return gql_optimizer.query(queryset.filter(recipient=info.context.user), info)
