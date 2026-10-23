from collections.abc import Callable
from functools import partial
from typing import Any

import swapper
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.db.models import QuerySet
from django.utils.module_loading import import_string
from notifications.signals import notify

from baseapp_core.plugins import SharedServiceProvider

from .groups import is_registered_verb
from .tasks import send_push_notification
from .utils import can_user_receive_notification

DEFAULT_EMAIL_SENDER = "baseapp_notifications.utils.send_notification_email"


def get_email_sender() -> Callable[..., Any]:
    """The callable configured in ``BASEAPP_NOTIFICATIONS_EMAIL_SENDER``."""
    return import_string(
        getattr(settings, "BASEAPP_NOTIFICATIONS_EMAIL_SENDER", DEFAULT_EMAIL_SENDER)
    )


def get_recipients(recipient: Any) -> list[Any]:
    """Flatten a user, a list/tuple/set or QuerySet of users, or an auth ``Group`` into users."""
    if isinstance(recipient, QuerySet):
        return list(recipient)
    if isinstance(recipient, (list, tuple, set)):
        return [user for user in recipient if user is not None]
    if apps.is_installed("django.contrib.auth"):
        from django.contrib.auth.models import Group

        if isinstance(recipient, Group):
            return list(recipient.user_set.all())
    return [recipient]


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
        email_template=None,
        email_context=None,
        email_options=None,
        **kwargs,
    ) -> list[tuple[Any, Any]]:
        """Notify one or many recipients, honouring each one's notification settings.

        ``recipient`` is a user, a list/tuple/set or QuerySet of users, or an auth ``Group``.
        ``email_template``, ``email_context`` and ``email_options`` reach only the email sender;
        they are never stored in ``Notification.data`` nor sent to the push task.
        Returns the ``notify.send`` results of every recipient, concatenated.
        """
        if getattr(
            settings, "BASEAPP_NOTIFICATIONS_REQUIRE_REGISTERED_VERBS", False
        ) and not is_registered_verb(verb):
            raise ImproperlyConfigured(
                f"Notification verb {verb!r} does not belong to a registered notification group."
            )

        notifications = []
        for user in get_recipients(recipient):
            notifications.extend(
                self._send_to_recipient(
                    sender,
                    user,
                    verb,
                    description=description,
                    action_object=action_object,
                    target=target,
                    add_to_history=add_to_history,
                    send_push=send_push,
                    send_email=send_email,
                    email_subject=email_subject,
                    email_message=email_message,
                    push_title=push_title,
                    push_description=push_description,
                    email_template=email_template,
                    email_context=email_context,
                    email_options=email_options,
                    **kwargs,
                )
            )
        return notifications

    def _send_to_recipient(
        self,
        sender,
        recipient,
        verb,
        description,
        action_object,
        target,
        add_to_history,
        send_push,
        send_email,
        email_subject,
        email_message,
        push_title,
        push_description,
        email_template=None,
        email_context=None,
        email_options=None,
        **kwargs,
    ) -> list[tuple[Any, Any]]:
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

            self._send_email(
                recipient,
                notification,
                sender=sender,
                verb=verb,
                action_object=action_object,
                description=description,
                target=target,
                add_to_history=add_to_history,
                send_push=send_push,
                email_subject=email_subject or description,
                email_message=email_message or description,
                email_template=email_template,
                email_context=email_context,
                email_options=email_options,
                **kwargs,
            )

        if send_push and can_user_receive_notification(
            recipient.id, verb, NotificationSetting.NotificationChannelTypes.PUSH
        ):
            # Queue after commit so the worker sees committed data and a rollback sends nothing.
            transaction.on_commit(
                partial(
                    send_push_notification.delay,
                    recipient.id,
                    push_title=push_title,
                    push_description=push_description or description,
                    # TO DO:
                    # serialize all objects so devices can use this data if necessary
                    **kwargs,
                )
            )

        return notifications

    @staticmethod
    def _send_email(recipient: Any, notification: Any, **context: Any) -> None:
        """Call the configured email sender and mark ``notification`` as emailed."""
        sent = get_email_sender()(recipient, notification, **context)

        # A sender returns False when it decided not to send.
        if notification and sent is not False:
            notification.emailed = True
            notification.save(update_fields=["emailed"])
