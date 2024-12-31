import swapper
from django.contrib import admin

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")


@admin.register(ContentPost)
class ContentPostAdmin(admin.ModelAdmin):
    search_fields = ("content",)
    raw_id_fields = ("author",)
    list_display = (
        "id",
        "author",
        "content"
    )
