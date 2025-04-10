import channels_graphql_ws
import graphene

from .object_types import NotificationNode


class OnNotificationChange(channels_graphql_ws.Subscription):
    created_notification = graphene.Field(NotificationNode._meta.connection.Edge)
    updated_notification = graphene.Field(NotificationNode)
    deleted_notification_id = graphene.ID()

    @staticmethod
    def subscribe(root, info):
        user = info.context.channels_scope["user"]
        if not user.is_authenticated:
            return []
        return [str(user.pk)]

    @staticmethod
    def publish(payload, info):
        created_notification = payload.get("created_notification", None)
        updated_notification = payload.get("updated_notification", None)
        deleted_notification_id = payload.get("deleted_notification_id", None)

        user = info.context.channels_scope["user"]

        if not user.is_authenticated:
            return None

        if created_notification:
            created_notification = NotificationNode._meta.connection.Edge(node=created_notification)

        return OnNotificationChange(
            created_notification=created_notification,
            updated_notification=updated_notification,
            deleted_notification_id=deleted_notification_id,
        )

    @classmethod
    def send_created_notification(cls, notification):
        cls.broadcast(
            group=str(notification.recipient_id),
            payload={"created_notification": notification},
        )

    @classmethod
    def send_updated_notification(cls, notification):
        cls.broadcast(
            group=str(notification.recipient_id),
            payload={"updated_notification": notification},
        )

    @classmethod
    def send_delete_notification(cls, recipient_id, notification_id):
        cls.broadcast(
            group=str(recipient_id),
            payload={"deleted_notification_id": notification_id},
        )


class NotificationsSubscription:
    on_notification_change = OnNotificationChange.Field()
