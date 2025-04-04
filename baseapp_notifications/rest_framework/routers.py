from push_notifications.api.rest_framework import (
    APNSDeviceAuthorizedViewSet,
    GCMDeviceAuthorizedViewSet,
    WebPushDeviceAuthorizedViewSet,
    WNSDeviceAuthorizedViewSet,
)

from baseapp_core.rest_framework.routers import DefaultRouter

notifications_router = DefaultRouter(trailing_slash=False)

notifications_router.register(
    r"push-notifications/apns", APNSDeviceAuthorizedViewSet, basename="apns"
)
notifications_router.register(r"push-notifications/gcm", GCMDeviceAuthorizedViewSet, basename="gcm")
notifications_router.register(r"push-notifications/wns", WNSDeviceAuthorizedViewSet, basename="wns")
notifications_router.register(
    r"push-notifications/web", WebPushDeviceAuthorizedViewSet, basename="web"
)
