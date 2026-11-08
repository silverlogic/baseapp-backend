from collections.abc import AsyncGenerator

import strawberry
from strawberry.types import Info

from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.subscriptions import listen, subscription_group

from .types import NotificationLazyType


@strawberry.type(name="OnNotificationChange")
class OnNotificationChange:
    created_notification: Edge[NotificationLazyType] | None = None
    updated_notification: NotificationLazyType | None = None
    deleted_notification_id: strawberry.ID | None = None


@strawberry.type
class NotificationsSubscription:
    @strawberry.subscription
    async def on_notification_change(
        self, info: Info
    ) -> AsyncGenerator[OnNotificationChange | None, None]:
        user = info.context.user
        groups = [str(user.pk)] if user.is_authenticated else []
        channel_groups = [subscription_group("OnNotificationChange", g) for g in groups]
        async for payload in listen(info, channel_groups):
            if not info.context.user.is_authenticated:
                yield None
                continue
            created = payload.get("created_notification")
            yield OnNotificationChange(
                created_notification=Edge(node=created, cursor=None) if created else None,
                updated_notification=payload.get("updated_notification"),
                deleted_notification_id=payload.get("deleted_notification_id"),
            )
