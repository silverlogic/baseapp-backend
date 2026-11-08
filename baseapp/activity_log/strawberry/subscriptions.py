from collections.abc import AsyncGenerator

import strawberry
from channels.db import database_sync_to_async
from strawberry.types import Info

from baseapp_core.graphql import get_obj_from_relay_id
from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.subscriptions import listen, subscription_group

from .types import ActivityLogLazyType


@strawberry.type(name="OnNewActivityLogMessage")
class OnNewActivityLogMessage:
    message: Edge[ActivityLogLazyType] | None = None


def _groups(info: Info, room_id: str) -> list[str]:
    user = info.context.user
    if not user.is_authenticated:
        return []
    room = get_obj_from_relay_id(info, room_id)
    if not user.has_perm("activity_log.view_activitylog", room):
        return []
    return [room_id]


@strawberry.type
class ActivityLogSubscriptions:
    """Not part of either schema yet: Graphene's plugin does not register it either."""

    @strawberry.subscription
    async def on_new_activity_log(
        self, info: Info, room_id: strawberry.ID
    ) -> AsyncGenerator[OnNewActivityLogMessage | None, None]:
        groups = await database_sync_to_async(_groups)(info, room_id)
        channel_groups = [subscription_group("OnNewActivityLogMessage", g) for g in groups]
        async for payload in listen(info, channel_groups):
            if not info.context.user.is_authenticated:
                yield None
                continue
            yield OnNewActivityLogMessage(message=Edge(node=payload["message"], cursor=None))
