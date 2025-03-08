from baseapp_core.rest_framework.routers import DefaultRouter

from .views import (
    StripeCustomerViewset,
    StripeProductViewset,
    StripeSubscriptionViewset,
    StripeWebhookViewset,
)

payments_router = DefaultRouter(trailing_slash=False)

payments_router.register(r"stripe/subscriptions", StripeSubscriptionViewset, basename="payments")
payments_router.register(r"stripe/customers", StripeCustomerViewset, basename="customers")
payments_router.register(r"stripe/products", StripeProductViewset, basename="products")
payments_router.register(r"stripe/webhooks", StripeWebhookViewset, basename="webhooks-stripe")
