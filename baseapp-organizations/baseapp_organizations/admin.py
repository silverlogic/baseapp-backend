from django.contrib import admin

import swapper

Organization = swapper.load_model("baseapp_organizations", "Organization")


class AbstractOrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "profile",
    )
