import swapper
from django.contrib import admin

Profile = swapper.load_model("baseapp_profiles", "Profile")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("id", "name", "target", "created", "modified")
