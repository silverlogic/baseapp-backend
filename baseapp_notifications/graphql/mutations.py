import graphene
import swapper
from django.utils.translation import gettext_lazy as _

from baseapp_core.graphql import RelayMutation, login_required
from baseapp_core.graphql.utils import get_pk_from_relay_id

from .object_types import NotificationChannelTypesEnum, NotificationsInterface

Notification = swapper.load_model("notifications", "Notification")
NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
NotificationNode = Notification.get_graphql_object_type()
NotificationSettingNode = NotificationSetting.get_graphql_object_type()


class NotificationsMarkAllAsRead(RelayMutation):
    recipient = graphene.Field(NotificationsInterface)

    class Input:
        read = graphene.Boolean(required=True, description=_("Mark as read or unread"))

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, read, **input):
        qs = Notification.objects.filter(recipient=info.context.user)

        if read:
            qs.mark_all_as_read()
        else:
            qs.mark_all_as_unread()

        return NotificationsMarkAllAsRead(
            recipient=info.context.user,
        )


class NotificationsMarkAsRead(RelayMutation):
    recipient = graphene.Field(NotificationsInterface)
    notifications = graphene.List(NotificationNode)

    class Input:
        read = graphene.Boolean(required=True, description=_("Mark as read or unread"))
        notification_ids = graphene.List(graphene.NonNull(graphene.ID))

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, notification_ids, read, **input):
        notifications_ids = [
            get_pk_from_relay_id(notification_relay_id)
            for notification_relay_id in notification_ids
        ]

        qs = Notification.objects.filter(pk__in=notifications_ids, recipient=info.context.user)

        if read:
            qs.mark_all_as_read()
        else:
            qs.mark_all_as_unread()

        return NotificationsMarkAsRead(
            notifications=qs,
            recipient=info.context.user,
        )


class NotificationSettingToggle(RelayMutation):
    notification_setting = graphene.Field(NotificationSettingNode)

    class Input:
        verb = graphene.String(required=True)
        channel = graphene.Field(NotificationChannelTypesEnum, required=True)

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, verb, channel, **input):
        # Determine if a setting other than 'ALL' exists for the given verb
        is_channel_all = channel == NotificationSetting.NotificationChannelTypes.ALL

        # Create or update the notification setting
        notification_setting, created = NotificationSetting.objects.get_or_create(
            user=info.context.user,
            verb=verb,
            channel=channel,
            defaults={"is_active": False},
        )

        if not created:
            notification_setting.is_active = not notification_setting.is_active
            notification_setting.save(update_fields=["is_active"])

        # Update other settings based on 'ALL' channel logic
        if is_channel_all:
            has_non_active_setting = (
                NotificationSetting.objects.filter(
                    user=info.context.user, verb=verb, is_active=False
                )
                .exclude(channel=NotificationSetting.NotificationChannelTypes.ALL)
                .exists()
            )
            if has_non_active_setting:
                # If a non-active setting exists, update 'ALL' setting to False
                NotificationSetting.objects.filter(
                    user=info.context.user,
                    verb=verb,
                    channel=NotificationSetting.NotificationChannelTypes.ALL,
                ).update(is_active=False)
            # Update all settings to match the 'ALL' setting
            NotificationSetting.objects.filter(user=info.context.user, verb=verb).update(
                is_active=notification_setting.is_active
            )
        else:
            # If the current channel is not 'ALL', ensure 'ALL' settings are updated to match
            NotificationSetting.objects.filter(
                user=info.context.user,
                verb=verb,
                channel=NotificationSetting.NotificationChannelTypes.ALL,
            ).update(is_active=notification_setting.is_active)

        return NotificationSettingToggle(notification_setting=notification_setting)


class NotificationsMutations(object):
    notifications_mark_as_read = NotificationsMarkAsRead.Field()
    notifications_mark_all_as_read = NotificationsMarkAllAsRead.Field()
    notification_setting_toggle = NotificationSettingToggle.Field()
