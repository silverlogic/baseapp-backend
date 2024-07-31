import swapper
from django.contrib import admin

RateModel = swapper.load_model("baseapp_ratings", "Rate")


@admin.register(RateModel)
class RatingAdmin(admin.ModelAdmin):
    search_fields = ("user__first_name", "user__last_name", "profile__name")
    raw_id_fields = ("user", "profile")
    list_display = (
        "id",
        "target",
        "user",
        "profile",
        "value",
        "created",
    )
