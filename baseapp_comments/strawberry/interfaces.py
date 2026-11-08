from collections.abc import Iterable
from typing import Any

import strawberry
import strawberry_django
import swapper
from django.conf import settings
from django.db.models import Model, Q
from strawberry.types import Info

from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    CountedConnection,
    Node,
    model_from_info,
    type_for_model,
)
from baseapp_core.strawberry.connections import connection

from ..models import default_comments_count
from .filters import CommentFilter

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label
CommentLazyType = type_for_model(Comment)


@strawberry.type(name="CommentsCount")
class CommentsCount:
    total: int | None = None
    main: int | None = None
    replies: int | None = None
    pinned: int | None = None
    reported: int | None = None


def _metadata_annotation(name: str) -> dict[str, Any]:
    """Optimizer hint: annotate one commentable metadata column on the implementing model."""

    def annotation(info: Info) -> Any:
        service = shared_services.get("commentable_metadata")
        return service.get_annotations(model_from_info(info))[name]

    return {name: annotation}


def _can_view_comments(root: Model, info: Info) -> bool:
    service = shared_services.get("commentable_metadata")
    if service and not service.is_comments_enabled(root):
        return False
    if not getattr(settings, "BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS", True):
        return info.context.user.is_authenticated
    return True


@strawberry.interface(name="CommentsInterface")
class CommentsInterface(Node):
    """Comments fields for any DocumentId-aware model. Optimizer hints live on the fields."""

    @strawberry_django.field(annotate=_metadata_annotation("_commentable_comments_count"))
    def comments_count(self, info: Info) -> CommentsCount:
        if service := shared_services.get("commentable_metadata"):
            counts = service.get_comments_count(self)
        else:
            counts = default_comments_count()
        return CommentsCount(**{k: v for k, v in counts.items() if hasattr(CommentsCount, k)})

    @connection(
        CountedConnection[CommentLazyType] | None,
        filterset_class=CommentFilter,
        annotate=_metadata_annotation("_commentable_is_comments_enabled"),
    )
    def comments(self, info: Info) -> Iterable[Model]:
        if not _can_view_comments(self, info):
            return Comment.objects.none()
        if isinstance(self, Comment):
            # A comment lists its replies plus, when it is itself a target, its top-level comments.
            queryset = Comment.objects_visible.filter(
                Q(in_reply_to_id=self.id)
                | Q(
                    target_document__content_type__app_label=app_label,
                    target_document__content_type__model=Comment._meta.model_name,
                    target_document__object_id=self.id,
                    in_reply_to__isnull=True,
                )
            )
        else:
            queryset = Comment.objects_visible.for_target(self, root_only=True)
        if service := shared_services.get("blocks.lookup"):
            queryset = service.exclude_blocked_from_foreign_queryset(queryset, info)
        return queryset

    @strawberry_django.field(annotate=_metadata_annotation("_commentable_is_comments_enabled"))
    def is_comments_enabled(self, info: Info) -> bool:
        if service := shared_services.get("commentable_metadata"):
            return service.is_comments_enabled(self)
        return True
