from baseapp_core.rest_framework.routers import DefaultRouter
from .views import StripePaymentsViewset

payments_router = DefaultRouter(trailing_slash=False)

payments_router.register(r"stripe", StripePaymentsViewset, basename="payments")
