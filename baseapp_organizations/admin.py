import swapper
from django.contrib import admin

from baseapp_profiles.models import update_or_create_profile

Organization = swapper.load_model("baseapp_organizations", "Organization")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "profile",
    )
    search_fields = (
        "name",
        "profile__name",
    )
    autocomplete_fields = ("profile",)
    readonly_fields = ("profile",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        update_or_create_profile(obj, request.user, obj.name)
