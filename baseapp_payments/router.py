from baseapp_core.rest_framework.routers import DefaultRouter

from .purchases import purchases_enabled
from .views import (
    StripeCustomerViewset,
    StripeProductViewset,
    StripePurchaseViewset,
    StripeSubscriptionViewset,
    StripeWebhookViewset,
)

payments_router = DefaultRouter(trailing_slash=True)
# Master routed these without a trailing slash, so every Stripe endpoint already
# registered in a dashboard points at the unslashed URL. Stripe does not follow
# redirects and counts a 301 as a failed delivery, so requiring the slash would
# silently stop webhook delivery on every existing deployment. `/?` accepts both.
payments_router.trailing_slash = "/?"

payments_router.register(
    r"stripe/subscriptions", StripeSubscriptionViewset, basename="subscriptions"
)
payments_router.register(r"stripe/customers", StripeCustomerViewset, basename="customers")
payments_router.register(r"stripe/products", StripeProductViewset, basename="products")
payments_router.register(r"stripe/webhooks", StripeWebhookViewset, basename="webhooks-stripe")
# One-time purchases are optional: the route exists only when the project configured the
# Purchase and PurchaseLine models.
if purchases_enabled():
    payments_router.register(r"stripe/purchases", StripePurchaseViewset, basename="purchases")
