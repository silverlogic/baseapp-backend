import graphene
import swapper
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from baseapp_core.graphql import ErrorType, RelayMutation, login_required
from baseapp_core.graphql.utils import get_pk_from_relay_id

from ..groups import get_notification_group
from ..utils import get_notification_group_states, set_notification_group_setting
from .object_types import (
    NotificationChannelTypesEnum,
    NotificationSettingGroup,
    NotificationsInterface,
)

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
    def mutate_and_get_payload(cls, root, info, read, **input) -> "NotificationsMarkAllAsRead":
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
    def mutate_and_get_payload(
        cls, root, info, notification_ids, read, **input
    ) -> "NotificationsMarkAsRead":
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
    def mutate_and_get_payload(
        cls, root, info, verb, channel, **input
    ) -> "NotificationSettingToggle":
        # A registered group key gets the same audience and lock checks as
        # notificationSettingsUpdate.
        group = get_notification_group(verb)
        message = None
        if group is not None and not group.is_visible_to(info.context.user):
            message = _("Unknown notification group: %(group)s") % {"group": verb}
        elif group is not None and group.is_locked:
            message = _("Notification group %(group)s cannot be changed") % {"group": verb}
        if message is not None:
            return NotificationSettingToggle(
                errors=[ErrorType(field="verb", messages=[str(message)])]
            )

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


class NotificationSettingGroupChannelInput(graphene.InputObjectType):
    group = graphene.String(required=True, description=_("Key of a registered notification group."))
    channel = NotificationChannelTypesEnum(
        required=True, description=_("ALL sets every channel of the group at once.")
    )
    is_active = graphene.Boolean(required=True)


class NotificationSettingsUpdate(RelayMutation):
    """Set the viewer's notification-group preferences.

    Idempotent: each entry sets a value, it never toggles. The whole input is rejected when an
    entry names an unknown group (or one outside the viewer's audience), a locked group, or a
    channel the group does not offer.
    """

    groups = graphene.List(
        graphene.NonNull(NotificationSettingGroup),
        description=_("The changed groups with their resulting state."),
    )
    recipient = graphene.Field(NotificationsInterface)

    class Input:
        settings = graphene.List(
            graphene.NonNull(NotificationSettingGroupChannelInput), required=True
        )

    @classmethod
    @login_required
    def mutate_and_get_payload(cls, root, info, settings, **input) -> "NotificationSettingsUpdate":
        user = info.context.user
        channel_all = int(NotificationSetting.NotificationChannelTypes.ALL)

        changes = []
        messages = []
        for setting in settings:
            group = get_notification_group(setting.group)
            channel = int(setting.channel)
            if group is None or not group.is_visible_to(user):
                messages.append(
                    _("Unknown notification group: %(group)s") % {"group": setting.group}
                )
            elif group.is_locked:
                messages.append(
                    _("Notification group %(group)s cannot be changed") % {"group": group.key}
                )
            elif channel != channel_all and channel not in group.channels:
                messages.append(
                    _("Notification group %(group)s has no %(channel)s channel")
                    % {
                        "group": group.key,
                        "channel": NotificationSetting.NotificationChannelTypes(channel).label,
                    }
                )
            else:
                changes.append((group, channel, setting.is_active))

        if messages:
            return NotificationSettingsUpdate(
                errors=[ErrorType(field="settings", messages=[str(m) for m in messages])]
            )

        with transaction.atomic():
            for group, channel, is_active in changes:
                set_notification_group_setting(user, group, channel, is_active)

        changed_groups = list({group.key: group for group, _channel, _active in changes}.values())
        return NotificationSettingsUpdate(
            groups=get_notification_group_states(user, changed_groups),
            recipient=user,
        )


class NotificationsMutations(object):
    notifications_mark_as_read = NotificationsMarkAsRead.Field()
    notifications_mark_all_as_read = NotificationsMarkAllAsRead.Field()
    notification_setting_toggle = NotificationSettingToggle.Field()
    notification_settings_update = NotificationSettingsUpdate.Field()
