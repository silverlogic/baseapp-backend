import swapper
from django.apps import apps
from notifications.signals import notify

from baseapp_core.plugins import SharedServiceProvider

from .tasks import send_push_notification
from .utils import can_user_receive_notification, send_email_notification


class NotificationService(SharedServiceProvider):
    @property
    def service_name(self) -> str:
        return "notifications"

    def is_available(self) -> bool:
        return apps.is_installed("baseapp_notifications")

    def send_notification(
        self,
        sender,
        recipient,
        verb,
        description=None,
        action_object=None,
        target=None,
        add_to_history=True,
        send_push=True,
        send_email=True,
        email_subject=None,
        email_message=None,
        push_title=None,
        push_description=None,
        **kwargs,
    ):
        NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")
        notifications = []

        if add_to_history and can_user_receive_notification(
            recipient.id, verb, NotificationSetting.NotificationChannelTypes.IN_APP
        ):
            notifications = notify.send(
                sender=sender,
                recipient=recipient,
                verb=verb,
                action_object=action_object,
                description=description,
                target=target,
                **kwargs,
            )

        if send_email and can_user_receive_notification(
            recipient.id, verb, NotificationSetting.NotificationChannelTypes.EMAIL
        ):
            notification = (
                notifications[0][1][0]
                if len(notifications) > 0
                and len(notifications[0]) > 1
                and len(notifications[0][1]) > 0
                else None
            )

            send_email_notification(
                to=recipient.email,
                context=dict(
                    notification=notification,
                    sender=sender,
                    recipient=recipient,
                    verb=verb,
                    action_object=action_object,
                    description=description,
                    target=target,
                    add_to_history=add_to_history,
                    send_push=send_push,
                    email_subject=email_subject or description,
                    email_message=email_message or description,
                    **kwargs,
                ),
            )

            if notification:
                notification.emailed = True
                notification.save(update_fields=["emailed"])

        if send_push and can_user_receive_notification(
            recipient.id, verb, NotificationSetting.NotificationChannelTypes.PUSH
        ):
            send_push_notification.delay(
                recipient.id,
                push_title=push_title,
                push_description=push_description or description,
                # TO DO:
                # serialize all objects so devices can use this data if necessary
                **kwargs,
            )

        return notifications
