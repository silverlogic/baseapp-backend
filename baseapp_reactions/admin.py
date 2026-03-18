import swapper
from django.contrib import admin

from baseapp_core.plugins import apply_if_installed

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    search_fields = (
        "reaction_type",
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
        "reaction_type",
        "user",
        *apply_if_installed("baseapp_profiles", ["profile"]),
    )
