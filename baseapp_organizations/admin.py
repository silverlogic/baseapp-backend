import swapper
from django.contrib import admin

from .services import OrganizationService

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

    def save_model(self, request, obj, form, change) -> None:
        super().save_model(request, obj, form, change)
        # The profile's name follows the organization's through a DB trigger, so only a
        # missing profile needs creating. The admin who creates it becomes its owner.
        OrganizationService.ensure_profile(obj, owner=request.user)
