from baseapp_core.rest_framework.routers import DefaultRouter
from baseapp_payments.views import StripePaymentsViewSet

payments_router = DefaultRouter(trailing_slash=False)

payments_router.register(r"payments", StripePaymentsViewSet, basename="payments")
