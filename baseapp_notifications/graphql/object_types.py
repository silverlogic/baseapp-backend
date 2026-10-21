from typing import TYPE_CHECKING

import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.utils.translation import gettext_lazy as _
from graphene.types.generic import GenericScalar
from graphene_django import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model

from ..groups import list_notification_groups
from ..utils import can_user_receive_notification, get_notification_group_states
from .filters import NotificationFilter

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from baseapp_notifications.models import (
        AbstractNotification,
        AbstractNotificationSetting,
    )

    from ..utils import NotificationGroupState

Notification = swapper.load_model("notifications", "Notification")
NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
NotificationChannelTypesEnum = graphene.Enum.from_enum(NotificationSetting.NotificationChannelTypes)


class NotificationSettingGroupChannel(graphene.ObjectType):
    channel = graphene.Field(NotificationChannelTypesEnum, required=True)
    is_active = graphene.Boolean(
        required=True, description=_("Whether the viewer receives this group on this channel.")
    )


class NotificationSettingGroup(graphene.ObjectType):
    """A registered notification group with the viewer's preference per channel."""

    key = graphene.String(
        required=True, description=_("Group key; use it as `group` in mutations and filters.")
    )
    label = graphene.String(required=True)
    description = graphene.String()
    is_locked = graphene.Boolean(
        required=True, description=_("Locked groups are always delivered and cannot be changed.")
    )
    channels = graphene.List(graphene.NonNull(NotificationSettingGroupChannel), required=True)


class NotificationsInterface(RelayNode):
    notifications_unread_count = graphene.Int()
    notifications = DjangoFilterConnectionField(
        get_object_type_for_model(Notification), filterset_class=NotificationFilter
    )
    notification_settings = DjangoConnectionField(get_object_type_for_model(NotificationSetting))
    is_notification_setting_active = graphene.Boolean(
        verb=graphene.String(required=True),
        channel=NotificationChannelTypesEnum(required=True),
    )
    notification_setting_groups = graphene.List(
        graphene.NonNull(NotificationSettingGroup),
        required=True,
        description=_("Registered notification groups the viewer can configure."),
    )

    def resolve_notifications_unread_count(self, info) -> int:
        if info.context.user.is_authenticated and info.context.user == self:
            return Notification.objects.filter(recipient=self, unread=True).count()
        return 0

    def resolve_notifications(self, info, **kwargs) -> "QuerySet":
        if info.context.user.is_authenticated and info.context.user == self:
            return Notification.objects.filter(recipient=info.context.user).order_by(
                "-unread", "-timestamp"
            )
        return Notification.objects.none()

    def resolve_notification_settings(self, info, **kwargs) -> "QuerySet":
        if info.context.user.is_authenticated and info.context.user == self:
            return NotificationSetting.objects.filter(user=info.context.user)
        return NotificationSetting.objects.none()

    def resolve_is_notification_setting_active(self, info, verb, channel, **kwargs) -> bool:
        if info.context.user.is_authenticated and info.context.user == self:
            return can_user_receive_notification(info.context.user.id, verb, channel)
        return False

    def resolve_notification_setting_groups(self, info, **kwargs) -> list["NotificationGroupState"]:
        if info.context.user.is_authenticated and info.context.user == self:
            return get_notification_group_states(self, list_notification_groups(self))
        return []


class BaseNotificationNode:
    actor = graphene.Field(RelayNode)
    target = graphene.Field(RelayNode)
    action_object = graphene.Field(RelayNode)
    data = GenericScalar(required=False)

    class Meta:
        interfaces = (RelayNode,)
        model = Notification
        fields = "__all__"

    @classmethod
    def get_node(cls, info, id) -> "AbstractNotification | None":
        if not info.context.user.is_authenticated:
            return None

        try:
            queryset = cls.get_queryset(cls._meta.model.objects, info)
            return queryset.get(id=id, recipient=info.context.user)
        except cls._meta.model.DoesNotExist:
            return None

    @classmethod
    def get_queryset(cls, queryset, info) -> "QuerySet":
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
        interfaces = (RelayNode,)

    @classmethod
    def get_queryset(cls, queryset, info) -> "QuerySet":
        if not info.context.user.is_authenticated:
            return queryset.none()

        return super().get_queryset(queryset.filter(user=info.context.user), info)

    @classmethod
    def get_node(cls, info, id) -> "AbstractNotificationSetting | None":
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
