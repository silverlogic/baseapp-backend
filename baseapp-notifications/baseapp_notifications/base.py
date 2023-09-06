from baseapp_core.graphql.models import RelayModel
from notifications.base.models import AbstractNotification as BaseAbstractNotification


class AbstractNotification(BaseAbstractNotification, RelayModel):
    class Meta(BaseAbstractNotification.Meta):
        abstract = True

    def save(self, *args, **kwargs):
        created = self._state.adding
        super().save(*args, **kwargs)

        from baseapp_notifications.graphql.subscriptions import OnNotificationChange

        if created:
            OnNotificationChange.send_created_notification(notification=self)
        else:
            OnNotificationChange.send_updated_notification(notification=self)

    def delete(self, *args, **kwargs):
        notification_relay_id = self.relay_id

        super().delete(*args, **kwargs)

        from baseapp_notifications.graphql.subscriptions import OnNotificationChange

        OnNotificationChange.send_delete_notification(
            recipient_id=self.recipient_id, notification_id=notification_relay_id
        )
