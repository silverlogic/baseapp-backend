import swapper
from baseapp_organizations.admin import AbstractOrganizationAdmin
from django.contrib import admin

Organization = swapper.load_model("baseapp_organizations", "Organization")


@admin.register(Organization)
class OrganizationAdmin(AbstractOrganizationAdmin):
    pass
