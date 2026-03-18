import swapper
from django.contrib import admin

from baseapp_core.plugins import apply_if_installed

RateModel = swapper.load_model("baseapp_ratings", "Rate")


@admin.register(RateModel)
class RatingAdmin(admin.ModelAdmin):
    search_fields = (
        "user__first_name",
        "user__last_name",
        *apply_if_installed("baseapp_profiles", ["profile__name"]),
    )
    raw_id_fields = (
        "user",
        *apply_if_installed("baseapp_profiles", ["profile"]),
    )
    list_display = (
        "id",
        "target",
        "user",
        *apply_if_installed("baseapp_profiles", ["profile"]),
        "value",
        "created",
    )
