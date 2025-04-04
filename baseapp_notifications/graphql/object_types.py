import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from graphene import relay
from graphene.types.generic import GenericScalar
from graphene_django import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import DjangoObjectType, get_object_type_for_model

from ..utils import can_user_receive_notification
from .filters import NotificationFilter

Notification = swapper.load_model("notifications", "Notification")
NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
NotificationChannelTypesEnum = graphene.Enum.from_enum(NotificationSetting.NotificationChannelTypes)


class NotificationsInterface(relay.Node):
    notifications_unread_count = graphene.Int()
    notifications = DjangoFilterConnectionField(
        get_object_type_for_model(Notification), filterset_class=NotificationFilter
    )
    notification_settings = DjangoConnectionField(get_object_type_for_model(NotificationSetting))
    is_notification_setting_active = graphene.Boolean(
        verb=graphene.String(required=True),
        channel=NotificationChannelTypesEnum(required=True),
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

    def resolve_notification_settings(self, info, **kwargs):
        if info.context.user.is_authenticated and info.context.user == self:
            return NotificationSetting.objects.filter(user=info.context.user)
        return NotificationSetting.objects.none()

    def resolve_is_notification_setting_active(self, info, verb, channel, **kwargs):
        if info.context.user.is_authenticated and info.context.user == self:
            return can_user_receive_notification(info.context.user.id, verb, channel)
        return False


class BaseNotificationNode:
    actor = graphene.Field(relay.Node)
    target = graphene.Field(relay.Node)
    action_object = graphene.Field(relay.Node)
    data = GenericScalar(required=False)

    class Meta:
        interfaces = (relay.Node,)
        model = Notification
        fields = "__all__"

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

        return super().get_queryset(queryset.filter(recipient=info.context.user), info)


class NotificationNode(
    BaseNotificationNode, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseNotificationNode.Meta):
        pass


class BaseNotificationSettingNode:
    channel = graphene.Field(NotificationChannelTypesEnum)

    class Meta:
        model = NotificationSetting
        fields = "__all__"
        interfaces = (relay.Node,)

    @classmethod
    def get_queryset(cls, queryset, info):
        if not info.context.user.is_authenticated:
            return queryset.none()

        return super().get_queryset(queryset.filter(user=info.context.user), info)

    @classmethod
    def get_node(cls, info, id):
        if not info.context.user.is_authenticated:
            return None

        try:
            queryset = cls.get_queryset(cls._meta.model.objects, info)
            return queryset.get(id=id, user=info.context.user)
        except cls._meta.model.DoesNotExist:
            return None


class NotificationSettingNode(
    BaseNotificationSettingNode, gql_optimizer.OptimizedDjangoObjectType, DjangoObjectType
):
    class Meta(BaseNotificationSettingNode.Meta):
        pass
