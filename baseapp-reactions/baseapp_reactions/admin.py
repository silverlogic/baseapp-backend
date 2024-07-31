import swapper
from django.contrib import admin

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    search_fields = ("reaction_type", "user__first_name", "user__last_name", "profile__name")
    raw_id_fields = ("user", "profile")
    list_display = ("id", "target", "reaction_type", "user", "profile")
