from django.contrib import admin

from .models import UserDevice


@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "ip_address", "device_id")
