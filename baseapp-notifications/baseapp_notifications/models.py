import swapper

from .base import AbstractNotification, AbstractNotificationSetting


class Notification(AbstractNotification):
    class Meta(AbstractNotification.Meta):
        abstract = False


class NotificationSetting(AbstractNotificationSetting):
    class Meta:
        swappable = swapper.swappable_setting("baseapp_notifications", "NotificationSetting")
