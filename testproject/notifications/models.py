from baseapp_notifications.models import (
    AbstractNotification,
    AbstractNotificationSetting,
)


class Notification(AbstractNotification):
    class Meta(AbstractNotification.Meta):
        pass


class NotificationSetting(AbstractNotificationSetting):
    class Meta(AbstractNotificationSetting.Meta):
        pass
