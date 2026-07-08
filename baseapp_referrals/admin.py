import swapper
from django.contrib import admin

UserReferral = swapper.load_model("baseapp_referrals", "UserReferral")


@admin.register(UserReferral)
class UserReferralAdmin(admin.ModelAdmin):
    list_display = ("id", "referrer", "referee")
    fields = ("referrer", "referee")
