import swapper
from django.contrib import admin

Plan = swapper.load_model("baseapp_payments", "Plan")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "price", "is_active")
