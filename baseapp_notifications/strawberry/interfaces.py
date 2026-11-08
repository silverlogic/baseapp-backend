from collections.abc import Iterable

import strawberry
import strawberry_django
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection, Node
from baseapp_core.strawberry.connections import connection

from ..graphql.filters import NotificationFilter
from ..utils import can_user_receive_notification
from .types import (
    Notification,
    NotificationChannelTypesEnum,
    NotificationLazyType,
    NotificationSetting,
    NotificationSettingLazyType,
)


def _is_self(root: Model, info: Info) -> bool:
    user = info.context.user
    return user.is_authenticated and user == root


@strawberry.interface(name="NotificationsInterface")
class NotificationsInterface(Node):
    @strawberry_django.field
    def notifications_unread_count(self, info: Info) -> int | None:
        if _is_self(self, info):
            return Notification.objects.filter(recipient=self, unread=True).count()
        return 0

    @connection(CountedConnection[NotificationLazyType] | None, filterset_class=NotificationFilter)
    def notifications(self, info: Info) -> Iterable[Model]:
        if _is_self(self, info):
            return Notification.objects.filter(recipient=info.context.user).order_by(
                "-unread", "-timestamp"
            )
        return Notification.objects.none()

    @connection(CountedConnection[NotificationSettingLazyType] | None)
    def notification_settings(self, info: Info) -> Iterable[Model]:
        if _is_self(self, info):
            return NotificationSetting.objects.filter(user=info.context.user)
        return NotificationSetting.objects.none()

    @strawberry_django.field
    def is_notification_setting_active(
        self, info: Info, verb: str, channel: NotificationChannelTypesEnum
    ) -> bool | None:
        if _is_self(self, info):
            return can_user_receive_notification(info.context.user.id, verb, channel)
        return False
