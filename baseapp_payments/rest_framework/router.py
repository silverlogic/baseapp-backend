from baseapp_core.rest_framework.routers import DefaultRouter

from .customers.viewsets import StripeCustomerViewSet
from .payment_methods.viewsets import StripePaymentMethodViewSet
from .products.viewsets import StripeProductViewSet
from .subscriptions.viewsets import StripeSubscriptionViewSet
from .webhooks.viewsets import StripeWebhookViewSet

payments_router = DefaultRouter(trailing_slash=False)

payments_router.register(
    r"stripe/subscriptions", StripeSubscriptionViewSet, basename="subscriptions"
)
payments_router.register(r"stripe/customers", StripeCustomerViewSet, basename="customers")
payments_router.register(r"stripe/products", StripeProductViewSet, basename="products")
payments_router.register(r"stripe/webhooks", StripeWebhookViewSet, basename="webhooks-stripe")
payments_router.register(
    r"stripe/payment-methods", StripePaymentMethodViewSet, basename="payment-methods"
)
