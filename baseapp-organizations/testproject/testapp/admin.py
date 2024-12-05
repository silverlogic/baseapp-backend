import swapper
from django.contrib import admin

from baseapp_organizations.admin import AbstractOrganizationAdmin

Organization = swapper.load_model("baseapp_organizations", "Organization")


@admin.register(Organization)
class OrganizationAdmin(AbstractOrganizationAdmin):
    pass
