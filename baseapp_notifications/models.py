import swapper

from .base import AbstractNotification, AbstractNotificationSetting


class Notification(AbstractNotification):
    class Meta(AbstractNotification.Meta):
        abstract = False
        swappable = swapper.swappable_setting("notifications", "Notification")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import NotificationNode

        return NotificationNode


class NotificationSetting(AbstractNotificationSetting):
    class Meta:
        swappable = swapper.swappable_setting("baseapp_notifications", "NotificationSetting")

    @classmethod
    def get_graphql_object_type(cls):
        from .graphql.object_types import NotificationSettingNode

        return NotificationSettingNode
