from typing import Any

from baseapp_core.strawberry.subscriptions import broadcast, subscription_group

SUBSCRIPTION_NAME = "OnNotificationChange"


def _broadcast(recipient_id: Any, payload: dict[str, Any]) -> None:
    broadcast(subscription_group(SUBSCRIPTION_NAME, str(recipient_id)), payload)


def send_created_notification(notification: Any) -> None:
    """Publish `onNotificationChange { createdNotification }` to the recipient."""
    _broadcast(notification.recipient_id, {"created_notification": notification})


def send_updated_notification(notification: Any) -> None:
    """Publish `onNotificationChange { updatedNotification }` to the recipient."""
    _broadcast(notification.recipient_id, {"updated_notification": notification})


def send_delete_notification(recipient_id: Any, notification_id: str) -> None:
    """Publish `onNotificationChange { deletedNotificationId }` to the recipient."""
    _broadcast(recipient_id, {"deleted_notification_id": notification_id})
