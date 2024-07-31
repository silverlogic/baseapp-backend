import swapper
from django.contrib import admin

Profile = swapper.load_model("baseapp_profiles", "Profile")
ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")


class ProfileUserRoleInline(admin.TabularInline):
    model = ProfileUserRole
    extra = 1
    raw_id_fields = ("user",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("id", "name", "target", "created", "modified")
    raw_id_fields = ("owner",)
    inlines = [ProfileUserRoleInline]
