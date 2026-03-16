import swapper
from django.contrib import admin
from django.template.defaultfilters import truncatewords

from baseapp_core.plugins import apply_if_installed

Comment = swapper.load_model("baseapp_comments", "Comment")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    search_fields = ("body",)
    raw_id_fields = ("user", *apply_if_installed("baseapp_profiles", ["profile"]), "in_reply_to")
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

    def truncated_body(self, obj):
        return truncatewords(obj.body, 10)

    truncated_body.short_description = "body"
