import graphene
import swapper
from baseapp_core.graphql import RelayMutation, login_required
from baseapp_core.graphql.utils import get_pk_from_relay_id
from django.utils.translation import gettext_lazy as _

from .object_types import NotificationNode, NotificationsNode

Notification = swapper.load_model("notifications", "Notification")


class NotificationsMarkAllAsRead(RelayMutation):
    recipient = graphene.Field(NotificationsNode)

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
    recipient = graphene.Field(NotificationsNode)
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


class NotificationsMutations(object):
    notifications_mark_as_read = NotificationsMarkAsRead.Field()
    notifications_mark_all_as_read = NotificationsMarkAllAsRead.Field()
