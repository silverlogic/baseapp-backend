import swapper
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin, TabularInline
from baseapp_core.plugins import apply_if_installed, shared_services

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")


class ContentPostImagesInline(TabularInline):
    model = ContentPostImage
    extra = 0


@admin.register(ContentPost)
class ContentPostAdmin(ModelAdmin):
    list_display = (
        "id",
        "user",
        *apply_if_installed("baseapp_profiles", ["profile"]),
        "content",
        "is_reactions_enabled",
    )
    list_filter = ["created"]
    search_fields = ["id", *apply_if_installed("baseapp_profiles", ["profile"]), "user", "content"]
    inlines = [ContentPostImagesInline]

    @admin.display(boolean=True, description="Reactions enabled")
    def is_reactions_enabled(self, obj) -> bool:
        # Pulled from `ReactableMetadata` via the shared service
        if service := shared_services.get("reactable_metadata"):
            return service.is_reactions_enabled(obj)
        return True


@admin.register(ContentPostImage)
class ContentPostImageAdmin(ModelAdmin):
    list_display = ("id", "post", "image")
    search_fields = ["post__content", "post__id"]
