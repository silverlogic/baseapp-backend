import swapper
from django.contrib import admin

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("entity", "remote_customer_id")
    search_fields = ("entity", "remote_customer_id")
    readonly_fields = ("remote_customer_id",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "remote_customer_id",
        "remote_subscription_id",
    )
    search_fields = ("remote_customer_id", "remote_subscription_id")
    readonly_fields = ("remote_subscription_id", "remote_customer_id")
