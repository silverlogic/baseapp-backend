import swapper
from django.apps import apps
from django.contrib import admin

from baseapp_core.admin_helpers import ModelAdmin, TabularInline

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


class ProfileUserRoleInline(TabularInline):
    model = ProfileUserRole
    extra = 1
    raw_id_fields = ("user",)


profile_inlines = [ProfileUserRoleInline]

if apps.is_installed("baseapp_pages"):
    from baseapp_pages.admin import URLPathAdminInline

    profile_inlines.append(URLPathAdminInline)


@admin.register(Profile)
class ProfileAdmin(ModelAdmin):
    search_fields = ("name",)
    list_display = ("id", "name", "target", "created", "modified")
    raw_id_fields = ("owner",)
    inlines = profile_inlines
