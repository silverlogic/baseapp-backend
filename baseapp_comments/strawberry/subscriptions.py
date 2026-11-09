from collections.abc import AsyncGenerator
from typing import Any

import strawberry
from channels.db import database_sync_to_async
from django.conf import settings
from strawberry.types import Info

from baseapp_core.strawberry.connections import Edge
from baseapp_core.strawberry.subscriptions import listen, subscription_group

from .types import CommentLazyType


@strawberry.type(name="OnCommentChange")
class OnCommentChange:
    created_comment: Edge[CommentLazyType] | None = None
    updated_comment: CommentLazyType | None = None
    deleted_comment_id: strawberry.ID | None = None


def _can_anonymous_view_comments() -> bool:
    return getattr(settings, "BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS", True)


def _groups(user: Any, target_object_id: str | None) -> list[str]:
    """Channel groups a subscriber listens on (`all` needs `view_all_comment`)."""
    if not target_object_id and user.has_perm("baseapp_comments.view_all_comment"):
        return ["all"]
    if not _can_anonymous_view_comments() and not user.is_authenticated:
        return []
    return [target_object_id] if target_object_id else []


@strawberry.type
class CommentsSubscriptions:
    @strawberry.subscription
    async def on_comment_change(
        self, info: Info, target_object_id: strawberry.ID | None = None
    ) -> AsyncGenerator[OnCommentChange | None, None]:
        user = info.context.user
        groups = await database_sync_to_async(_groups)(user, target_object_id)
        groups = [subscription_group("OnCommentChange", group) for group in groups]
        async for payload in listen(info, groups):
            if not _can_anonymous_view_comments() and not user.is_authenticated:
                yield None
                continue
            created = payload.get("created_comment")
            yield OnCommentChange(
                created_comment=Edge(node=created, cursor=None) if created else None,
                updated_comment=payload.get("updated_comment"),
                deleted_comment_id=payload.get("deleted_comment_id"),
            )
