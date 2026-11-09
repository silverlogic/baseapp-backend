import strawberry
import swapper
from django.utils.translation import gettext_lazy as _
from strawberry import UNSET
from strawberry.types import Info

from baseapp_core.graphql.utils import get_pk_from_relay_id
from baseapp_core.strawberry import RelayMutationInput, RelayMutationPayload
from baseapp_core.strawberry.mutations import relay_mutation

from .interfaces import NotificationsInterface
from .types import (
    NotificationChannelTypesEnum,
    NotificationLazyType,
    NotificationSettingLazyType,
)

Notification = swapper.load_model("notifications", "Notification")
NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")

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


@strawberry.type
class NotificationsMutations:
    @relay_mutation(login_required=True)
    def notifications_mark_as_read(
        self, info: Info, input: NotificationsMarkAsReadInput
    ) -> NotificationsMarkAsReadPayload | None:
        notifications_ids = [get_pk_from_relay_id(relay_id) for relay_id in input.notification_ids]
        qs = Notification.objects.filter(pk__in=notifications_ids, recipient=info.context.user)

        if input.read:
            qs.mark_all_as_read()
        else:
            qs.mark_all_as_unread()

        return NotificationsMarkAsReadPayload(notifications=qs, recipient=info.context.user)

    @relay_mutation(login_required=True)
    def notifications_mark_all_as_read(
        self, info: Info, input: NotificationsMarkAllAsReadInput
    ) -> NotificationsMarkAllAsReadPayload | None:
        qs = Notification.objects.filter(recipient=info.context.user)

        if input.read:
            qs.mark_all_as_read()
        else:
            qs.mark_all_as_unread()

        return NotificationsMarkAllAsReadPayload(recipient=info.context.user)

    @relay_mutation(login_required=True)
    def notification_setting_toggle(
        self, info: Info, input: NotificationSettingToggleInput
    ) -> NotificationSettingTogglePayload | None:
        user = info.context.user
        verb = input.verb
        channel = input.channel
        ALL = NotificationSetting.NotificationChannelTypes.ALL
        is_channel_all = channel == ALL

        notification_setting, created = NotificationSetting.objects.get_or_create(
            user=user, verb=verb, channel=channel, defaults={"is_active": False}
        )

        if not created:
            notification_setting.is_active = not notification_setting.is_active
            notification_setting.save(update_fields=["is_active"])

        if is_channel_all:
            has_non_active_setting = (
                NotificationSetting.objects.filter(user=user, verb=verb, is_active=False)
                .exclude(channel=ALL)
                .exists()
            )
            if has_non_active_setting:
                NotificationSetting.objects.filter(user=user, verb=verb, channel=ALL).update(
                    is_active=False
                )
            # All channels follow the 'ALL' setting.
            NotificationSetting.objects.filter(user=user, verb=verb).update(
                is_active=notification_setting.is_active
            )
        else:
            NotificationSetting.objects.filter(user=user, verb=verb, channel=ALL).update(
                is_active=notification_setting.is_active
            )

        return NotificationSettingTogglePayload(notification_setting=notification_setting)
