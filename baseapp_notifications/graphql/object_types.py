import weakref
from typing import TYPE_CHECKING

import graphene
import graphene_django_optimizer as gql_optimizer
import swapper
from django.db.models import Model
from django.utils.translation import gettext_lazy as _
from graphene.types.generic import GenericScalar
from graphene_django import DjangoConnectionField
from graphene_django.filter import DjangoFilterConnectionField
from graphql import get_nullable_type, is_abstract_type

from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model

from ..groups import list_notification_groups
from ..utils import can_user_receive_notification, get_notification_group_states
from .filters import NotificationFilter

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from graphql import GraphQLInterfaceType, GraphQLSchema

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


def _accepts(
    schema: "GraphQLSchema", interface: "GraphQLInterfaceType", obj, info: graphene.ResolveInfo
) -> bool:
    """Whether a type of ``schema`` implementing ``interface`` accepts ``obj``.

    This is the ``is_type_of`` check graphql-core makes to resolve an abstract type at runtime.
    """
    for object_type in schema.get_possible_types(interface):
        if object_type.is_type_of is None:
            continue
        try:
            if object_type.is_type_of(obj, info) is True:
                return True
        except Exception:
            continue
    return False


# schema -> {(interface name, model): bool}. Django types only compare the model, so the answer
# is cached per model; a type whose own is_type_of accepts only some instances of a model would
# need its own resolver. Weak keys let rebuilt schemas (tests, autoreload) be collected.
_model_has_node_type: "weakref.WeakKeyDictionary[GraphQLSchema, dict[tuple, bool]]" = (
    weakref.WeakKeyDictionary()
)


def resolve_node_or_none(obj, info: graphene.ResolveInfo):
    """Return ``obj`` for a ``Node`` field, or ``None`` when no type in the schema represents it.

    Notifications point at arbitrary objects (generic foreign keys). Without this, an actor,
    target or action object whose model has no ``Node`` type fails the whole query with
    "Abstract type 'Node' must resolve to an Object type at runtime".
    """
    if obj is None or isinstance(obj, graphene.ObjectType):
        return obj
    interface = get_nullable_type(info.return_type)
    if not is_abstract_type(interface):
        return obj
    if not isinstance(obj, Model):
        return obj if _accepts(info.schema, interface, obj, info) else None

    cache = _model_has_node_type.setdefault(info.schema, {})
    key = (interface.name, type(obj))
    if key not in cache:
        cache[key] = _accepts(info.schema, interface, obj, info)
    return obj if cache[key] else None


class BaseNotificationNode:
    actor = graphene.Field(RelayNode)
    target = graphene.Field(RelayNode)
    action_object = graphene.Field(RelayNode)
    data = GenericScalar(required=False)

    @staticmethod
    @gql_optimizer.resolver_hints(model_field="actor")
    def resolve_actor(root, info: graphene.ResolveInfo):
        return resolve_node_or_none(root.actor, info)

    @staticmethod
    @gql_optimizer.resolver_hints(model_field="target")
    def resolve_target(root, info: graphene.ResolveInfo):
        return resolve_node_or_none(root.target, info)

    @staticmethod
    @gql_optimizer.resolver_hints(model_field="action_object")
    def resolve_action_object(root, info: graphene.ResolveInfo):
        return resolve_node_or_none(root.action_object, info)

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
