import swapper
from django.contrib import admin
from notifications.admin import NotificationAdmin  # noqa

NotificationSetting = swapper.load_model("baseapp_notifications", "NotificationSetting")


@admin.register(NotificationSetting)
class NotificationSettingAdmin(admin.ModelAdmin):
    list_display = ["user", "verb", "channel", "is_active", "created"]
    list_filter = ["channel", "is_active"]
    search_fields = ["user__username", "verb"]
