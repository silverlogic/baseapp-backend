import swapper
from django.contrib import admin

Follow = swapper.load_model("baseapp_follows", "Follow")


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("id", "actor", "target", "created", "target_is_following_back")
    list_filter = ("created",)
