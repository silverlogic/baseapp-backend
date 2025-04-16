import swapper
from django.contrib import admin

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")


@admin.register(ContentPost)
class ContentPostAdmin(admin.ModelAdmin):
    search_fields = ("content",)
    raw_id_fields = ("user", "profile")
    list_display = ("id", "user", "profile", "content")


@admin.register(ContentPostImage)
class ContentPostImageAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "image")
