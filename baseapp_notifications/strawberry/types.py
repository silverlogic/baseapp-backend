from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Model, QuerySet
from strawberry.types import Info

from baseapp_core.strawberry import Node, django_type, type_for_model
from baseapp_core.strawberry.enums import choices_enum, enum_from_choices
from baseapp_core.strawberry.scalars import GenericScalar

from ..filters import NotificationFilter

Notification = swapper.load_model("notifications", "Notification")
NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")

NotificationLazyType = type_for_model(Notification)
NotificationSettingLazyType = type_for_model(NotificationSetting)
NotificationLevelEnum = choices_enum(Notification, "level")
NotificationChannelTypesEnum = enum_from_choices(
    NotificationSetting.NotificationChannelTypes, "NotificationChannelTypes"
)


def _generic_relation(name: str) -> Any:
    def resolver(root: Model, info: Info) -> Any:
        return getattr(root, name)

    return strawberry_django.field(
        resolver=resolver,
        graphql_type=Optional[Node],
        only=[f"{name}_content_type_id", f"{name}_object_id"],
        prefetch_related=[name],
    )


@strawberry_django.type(Notification, name="AbstractNotification")
class AbstractNotificationType:
    """Notification fields, shared by the package type and project overrides."""

    level: NotificationLevelEnum
    unread: bool  # explicit: filter arguments read declared types, and inherited `auto` is Any
    actor_object_id: strawberry.auto
    verb: strawberry.auto
    description: strawberry.auto
    target_object_id: strawberry.auto
    action_object_object_id: strawberry.auto
    timestamp: strawberry.auto
    public: strawberry.auto
    deleted: strawberry.auto
    emailed: strawberry.auto
    data: GenericScalar | None
    actor: Node | None = _generic_relation("actor")
    target: Node | None = _generic_relation("target")
    action_object: Node | None = _generic_relation("action_object")
    pk: int | None = strawberry_django.field()

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        user = info.context.user
        if not user.is_authenticated:
            return queryset.none()
        return queryset.filter(recipient=user)

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        if not info.context.user.is_authenticated:
            return None
        return super().get_node(info, pk)


@django_type(Notification, filterset_class=NotificationFilter, relations="__all__")
class NotificationType(AbstractNotificationType, Node):
    pass


@strawberry_django.type(NotificationSetting, name="AbstractNotificationSetting")
class AbstractNotificationSettingType:
    """NotificationSetting fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto
    channel: NotificationChannelTypesEnum | None
    verb: strawberry.auto
    is_active: strawberry.auto
    pk: int | None = strawberry_django.field()

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        user = info.context.user
        if not user.is_authenticated:
            return queryset.none()
        return queryset.filter(user=user)

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        if not info.context.user.is_authenticated:
            return None
        return super().get_node(info, pk)


@django_type(NotificationSetting, relations="__all__")
class NotificationSettingType(AbstractNotificationSettingType, Node):
    pass
