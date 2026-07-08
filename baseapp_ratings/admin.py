import swapper
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin
from baseapp_core.plugins import apply_if_installed

RateModel = swapper.load_model("baseapp_ratings", "Rate")


@admin.register(RateModel)
class RatingAdmin(ModelAdmin):
    search_fields = (
        "user__first_name",
        "user__last_name",
        *apply_if_installed("baseapp_profiles", ["profile__name"]),
    )
    raw_id_fields = (
        "user",
        *apply_if_installed("baseapp_profiles", ["profile"]),
        "target_document",
    )
    list_display = (
        "id",
        "target",
        "user",
        *apply_if_installed("baseapp_profiles", ["profile"]),
        "value",
        "created",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "user",
                *apply_if_installed("baseapp_profiles", ["profile"]),
                "target_document__content_type",
            )
            .prefetch_related("target_document__content_object")
        )
