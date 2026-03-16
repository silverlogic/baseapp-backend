import swapper
from django.contrib import admin

from baseapp_core.plugins import apply_if_installed

Follow = swapper.load_model("baseapp_follows", "Follow")


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    raw_id_fields = (
        "user",
        *apply_if_installed("baseapp_profiles", ["actor"]),
        "target",
    )
    list_display = (
        "id",
        *apply_if_installed("baseapp_profiles", ["actor"]),
        "target",
        "created",
        "target_is_following_back",
    )
    list_filter = ("created",)
