from django.contrib import admin

import swapper

Reaction = swapper.load_model("baseapp_reactions", "Reaction")


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    search_fields = ("reaction_type", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)
    list_display = ("id", "target", "user", "reaction_type")
