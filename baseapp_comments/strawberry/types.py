from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import Model, QuerySet
from strawberry.types import Info

from baseapp_auth.strawberry.permissions import PermissionsInterface
from baseapp_core.graphql import resolve_document_content_object
from baseapp_core.plugins import (
    apply_if_installed,
    shared_services,
    strawberry_shared_interfaces,
)
from baseapp_core.strawberry import Node, django_type
from baseapp_core.strawberry.enums import enum_from_choices

from ..models import CommentStatus
from .filters import CommentFilter
from .interfaces import CommentLazyType, CommentsInterface

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label
CommentStatusEnum = enum_from_choices(CommentStatus, "CommentStatus")


@strawberry_django.type(Comment, name="AbstractComment")
class AbstractCommentType:
    """Comment fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto
    body: strawberry.auto
    language: str | None = strawberry_django.field(description="language used in the comment")
    is_edited: strawberry.auto
    is_pinned: strawberry.auto
    status: CommentStatusEnum | None
    pk: int | None = strawberry_django.field()

    @strawberry_django.field(
        graphql_type=Optional[CommentsInterface],
        only=["target_document_id"],
        select_related=["target_document__content_type"],
    )
    def target(self, info: Info) -> Any:
        if not self.target_document_id:
            return None
        return resolve_document_content_object(
            self.target_document, info, cache_attr="_comment_target_cache"
        )

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        if service := shared_services.get("blocks.lookup"):
            return service.exclude_blocked_from_foreign_queryset(queryset, info)
        return queryset

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if not info.context.user.has_perm(f"{app_label}.view_comment", node):
            return None
        return node


def comment_interfaces() -> tuple[type, ...]:
    return (
        CommentsInterface,
        PermissionsInterface,
        *strawberry_shared_interfaces.get(
            "ReactionsInterface",
            "MentionsInterface",
            "NodeActivityLogInterface",
            "FilesInterface",
        ),
        Node,
    )


# Columns read by the permission backend and the `comments` resolver.
@django_type(
    Comment,
    filterset_class=CommentFilter,
    relations=("user", "in_reply_to", *apply_if_installed("baseapp_profiles", ["profile"])),
    only=["status", "target_document_id", "in_reply_to_id", "user_id"],
)
class CommentType(AbstractCommentType, *comment_interfaces()):
    pass


__all__ = ["CommentLazyType", "CommentStatusEnum", "CommentType"]
