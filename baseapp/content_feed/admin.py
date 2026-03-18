import swapper
from django.contrib import admin

from baseapp_core.plugins import apply_if_installed

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")


@admin.register(ContentPost)
class ContentPostAdmin(admin.ModelAdmin):
    search_fields = ("content",)
    raw_id_fields = ("user", *apply_if_installed("baseapp_profiles", ["profile"]))
    list_display = ("id", "user", *apply_if_installed("baseapp_profiles", ["profile"]), "content")


@admin.register(ContentPostImage)
class ContentPostImageAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "image")
