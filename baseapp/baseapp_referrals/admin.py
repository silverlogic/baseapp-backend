from django.contrib import admin

from .models import UserReferral


class UserReferralAdmin(admin.ModelAdmin):
    list_display = ("id", "referrer", "referee")
    fields = ("referrer", "referee")


admin.site.register(UserReferral, UserReferralAdmin)
