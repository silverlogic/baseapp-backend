from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import swapper
from django.conf import settings
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from model_utils.models import TimeStampedModel
from notifications.base.models import AbstractNotification as BaseAbstractNotification
from notifications.base.models import NotificationQuerySet as BaseNotificationQuerySet

from baseapp_core.graphql.models import RelayModel
from baseapp_core.models import DocumentIdMixin

if TYPE_CHECKING:
    from baseapp_core.graphql import DjangoObjectType


class NotificationQuerySet(BaseNotificationQuerySet):
    """QuerySet for notifications that broadcasts GraphQL subscription events on bulk creation.

    Single-instance ``save``/``delete`` already broadcast via ``AbstractNotification``, but
    ``bulk_create`` bypasses ``save``, so this re-queries the created rows and emits a
    ``created`` subscription event for each one after the surrounding transaction commits.
    """

    def bulk_create(self, objs: Iterable[Any], *args: Any, **kwargs: Any) -> list[Any]:
        """Bulk-create notifications and broadcast a created event per row after commit."""
        result = super().bulk_create(objs, *args, **kwargs)

        from baseapp_notifications.graphql.subscriptions import OnNotificationChange

        pks = [n.pk for n in result if n.pk]
        Model = self.model
        db = self.db

        def broadcast() -> None:
            for notification in Model._default_manager.using(db).filter(pk__in=pks):
                OnNotificationChange.send_created_notification(notification=notification)

        transaction.on_commit(broadcast, using=db)
        return result


class AbstractNotification(BaseAbstractNotification, DocumentIdMixin, RelayModel):
    objects = NotificationQuerySet.as_manager()

    class Meta(BaseAbstractNotification.Meta):
        abstract = True
        # This model must reference "notifications.Notification" due to the dependency on django-notifications-community
        swappable = swapper.swappable_setting("notifications", "Notification")

    def save(self, *args, **kwargs) -> None:
        created = self._state.adding
        super().save(*args, **kwargs)

        from baseapp_notifications.graphql.subscriptions import OnNotificationChange

        pk = self.pk
        Notification = type(self)

        def broadcast() -> None:
            notification = Notification.objects.filter(pk=pk).first()
            if notification is None:
                return
            if created:
                OnNotificationChange.send_created_notification(notification=notification)
            else:
                OnNotificationChange.send_updated_notification(notification=notification)

        transaction.on_commit(broadcast)

    def delete(self, *args, **kwargs) -> None:
        notification_relay_id = self.relay_id

        super().delete(*args, **kwargs)

        from baseapp_notifications.graphql.subscriptions import OnNotificationChange

        OnNotificationChange.send_delete_notification(
            recipient_id=self.recipient_id, notification_id=notification_relay_id
        )

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
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
        def description(self) -> str:
            return self.label

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="notifications_settings", on_delete=models.CASCADE
    )
    channel = models.IntegerField(choices=NotificationChannelTypes.choices)
    verb = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    @classmethod
    def get_graphql_object_type(cls) -> type["DjangoObjectType"]:
        from .graphql.object_types import NotificationSettingNode

        return NotificationSettingNode
