from typing import TYPE_CHECKING

import swapper
from django.contrib import admin
from django.template.defaultfilters import truncatewords

from baseapp_core.admin_helpers import ModelAdmin
from baseapp_core.plugins import apply_if_installed

if TYPE_CHECKING:
    from django.db.models import QuerySet

Comment = swapper.load_model("baseapp_comments", "Comment")
CommentableMetadata = swapper.load_model("baseapp_comments", "CommentableMetadata")


@admin.register(Comment)
class CommentAdmin(ModelAdmin):
    search_fields = ("body",)
    raw_id_fields = (
        "user",
        *apply_if_installed("baseapp_profiles", ["profile"]),
        "in_reply_to",
        "target_document",
    )
    list_display = (
        "id",
        "user",
        *apply_if_installed("baseapp_profiles", ["profile"]),
        "target",
        "in_reply_to",
        "truncated_body",
        "status",
        "is_pinned",
        "created",
    )

    def get_queryset(self, request) -> "QuerySet":
        return (
            super()
            .get_queryset(request)
            .select_related(
                "user",
                *apply_if_installed("baseapp_profiles", ["profile"]),
                "in_reply_to",
                "target_document__content_type",
            )
            .prefetch_related("target_document__content_object")
        )

    def truncated_body(self, obj) -> str:
        return truncatewords(obj.body, 10)

    truncated_body.short_description = "body"


@admin.register(CommentableMetadata)
class CommentableMetadataAdmin(ModelAdmin):
    list_display = ("target", "is_comments_enabled", "comments_count")
    list_editable = ("is_comments_enabled",)
    search_fields = ("target__content_type__model",)
    raw_id_fields = ("target",)
