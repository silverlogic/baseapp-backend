from django.contrib import admin

from .models import IpRestriction, Role


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "slug",
    )
    search_fields = ("name", "slug")
    filter_horizontal = ("groups", "permissions", "exclude_permissions")


@admin.register(IpRestriction)
class IpRestrictionAdmin(admin.ModelAdmin):
    list_display = ("id", "ip_address", "is_whitelisted", "created_at", "modified_at")
    search_fields = ("ip_address",)
    filter_horizontal = ("unrestricted_roles",)
