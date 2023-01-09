from django.contrib import admin

from .models import Role


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
    )
    search_fields = ("name", "slug")
    filter_horizontal = ("groups", "permissions", "exclude_permissions")
