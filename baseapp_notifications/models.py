import swapper
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel
from notifications.base.models import AbstractNotification as BaseAbstractNotification

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin


class AbstractNotification(BaseAbstractNotification, DocumentIdMixin, RelayModel):
    class Meta(BaseAbstractNotification.Meta):
        abstract = True
        # This model must reference "notifications.Notification" due to the dependency on django-notifications-hq
        swappable = swapper.swappable_setting("notifications", "Notification")

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

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import NotificationNode

        return NotificationNode


class AbstractNotificationSetting(TimeStampedModel, DocumentIdMixin, RelayModel):
    class Meta:
        abstract = True
        swappable = swapper.swappable_setting("baseapp_notifications", "NotificationSetting")

    class NotificationChannelTypes(models.IntegerChoices):
        ALL = 0, _("All")
        EMAIL = 1, _("Email")
        PUSH = 2, _("Push")
        IN_APP = 3, _("In-App")

        @property
        def description(self):
            return self.label

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="notifications_settings", on_delete=models.CASCADE
    )
    channel = models.IntegerField(choices=NotificationChannelTypes.choices)
    verb = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import NotificationSettingNode

        return NotificationSettingNode
