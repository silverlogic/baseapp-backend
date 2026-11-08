import strawberry
from django.utils.translation import gettext_lazy as _
from strawberry import UNSET

from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.mutations import graphene_relay_mutation

from ..graphql import mutations as graphene_mutations
from .interfaces import NotificationsInterface
from .types import (
    NotificationChannelTypesEnum,
    NotificationLazyType,
    NotificationSettingLazyType,
)

READ_DESCRIPTION = str(_("Mark as read or unread"))


@strawberry.input(name="NotificationsMarkAsReadInput")
class NotificationsMarkAsReadInput(RelayMutationInput):
    read: bool = strawberry.field(description=READ_DESCRIPTION)
    notification_ids: list[strawberry.ID] | None = UNSET


@strawberry.type(name="NotificationsMarkAsReadPayload")
class NotificationsMarkAsReadPayload(RelayMutationPayload):
    recipient: NotificationsInterface | None = None
    notifications: list[NotificationLazyType | None] | None = None


@strawberry.input(name="NotificationsMarkAllAsReadInput")
class NotificationsMarkAllAsReadInput(RelayMutationInput):
    read: bool = strawberry.field(description=READ_DESCRIPTION)


@strawberry.type(name="NotificationsMarkAllAsReadPayload")
class NotificationsMarkAllAsReadPayload(RelayMutationPayload):
    recipient: NotificationsInterface | None = None


@strawberry.input(name="NotificationSettingToggleInput")
class NotificationSettingToggleInput(RelayMutationInput):
    verb: str
    channel: NotificationChannelTypesEnum


@strawberry.type(name="NotificationSettingTogglePayload")
class NotificationSettingTogglePayload(RelayMutationPayload):
    notification_setting: NotificationSettingLazyType | None = None


g = graphene_mutations


@strawberry.type
class NotificationsMutations:
    notifications_mark_as_read = graphene_relay_mutation(
        g.NotificationsMarkAsRead, NotificationsMarkAsReadInput, NotificationsMarkAsReadPayload
    )
    notifications_mark_all_as_read = graphene_relay_mutation(
        g.NotificationsMarkAllAsRead,
        NotificationsMarkAllAsReadInput,
        NotificationsMarkAllAsReadPayload,
    )
    notification_setting_toggle = graphene_relay_mutation(
        g.NotificationSettingToggle,
        NotificationSettingToggleInput,
        NotificationSettingTogglePayload,
    )
