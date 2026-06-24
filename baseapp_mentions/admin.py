import swapper
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin

Mention = swapper.load_model("baseapp_mentions", "Mention")


class BaseMentionAdmin(ModelAdmin):
    raw_id_fields = ("profile", "target_document")
    list_display = ("id", "profile", "get_target_object", "created")
    list_filter = ("created",)

    @admin.display(description="Target")
    def get_target_object(self, obj):
        # `DocumentIdTargetMixin.target` resolves the underlying content object.
        content_obj = obj.target
        return str(content_obj) if content_obj else f"DocumentId:{obj.target_document_id}"


@admin.register(Mention)
class MentionAdmin(BaseMentionAdmin):
    pass
