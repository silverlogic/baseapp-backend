import swapper
from django.conf import settings
from django.contrib import admin

Customer = swapper.load_model("baseapp_payments", "Customer")
Subscription = swapper.load_model("baseapp_payments", "Subscription")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("entity_id", "remote_customer_id")
    search_fields = ("entity_id", "remote_customer_id")
    readonly_fields = ("remote_customer_id",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer_id",
        "remote_subscription_id",
    )
    search_fields = ("customer_id", "remote_subscription_id")
    readonly_fields = ("remote_subscription_id", "customer_id")


# One-time purchases are optional; registered only when the project configured them.
if getattr(settings, "BASEAPP_PAYMENTS_PURCHASE_MODEL", None) and getattr(
    settings, "BASEAPP_PAYMENTS_PURCHASELINE_MODEL", None
):
    Purchase = swapper.load_model("baseapp_payments", "Purchase")
    PurchaseLine = swapper.load_model("baseapp_payments", "PurchaseLine")

    class PurchaseLineInline(admin.TabularInline):
        model = PurchaseLine
        extra = 0
        can_delete = False
        readonly_fields = (
            "remote_product_id",
            "remote_price_id",
            "description",
            "unit_amount",
            "quantity",
            "amount",
        )

    @admin.register(Purchase)
    class PurchaseAdmin(admin.ModelAdmin):
        list_display = ("id", "customer_id", "status", "total", "currency", "created")
        list_filter = ("status",)
        search_fields = ("remote_invoice_id", "customer__remote_customer_id")
        readonly_fields = (
            "customer",
            "status",
            "currency",
            "subtotal",
            "tax",
            "total",
            "remote_invoice_id",
            "paid_at",
            "failed_at",
        )
        inlines = [PurchaseLineInline]
