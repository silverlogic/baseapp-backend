from django.apps import apps

from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class NotificationsPlugin(BaseAppPlugin):
    """
    The Notifications plugin is used to send notifications to users.
    It depends on the django-notifications-hq package. But it must not activate the "notifications" app.
    """

    @property
    def name(self) -> str:
        return "baseapp_notifications"

    @property
    def package_name(self) -> str:
        return "baseapp_notifications"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            django_extra_settings={
                "DJANGO_NOTIFICATIONS_CONFIG": {"USE_JSONFIELD": True},
            },
            # GraphQL
            graphql_mutations=[
                "baseapp_notifications.graphql.mutations.NotificationsMutations",
            ],
            graphql_subscriptions=[
                "baseapp_notifications.graphql.subscriptions.NotificationsSubscription",
            ],
            # Plugin deps
            required_packages=[],
            optional_packages=[
                {
                    "push_notifications": "Used for push notifications. See baseapp_notifications/README.md for more details.",
                },
            ],
            # URLs
            v1_urlpatterns=self.v1_urlpatterns,
        )

    @staticmethod
    def v1_urlpatterns(include, path, re_path):
        if not apps.is_installed("push_notifications"):
            return []

        from push_notifications.api.rest_framework import (
            APNSDeviceAuthorizedViewSet,
            GCMDeviceAuthorizedViewSet,
            WebPushDeviceAuthorizedViewSet,
            WNSDeviceAuthorizedViewSet,
        )

        return [
            re_path(
                r"push-notifications/apns",
                APNSDeviceAuthorizedViewSet.as_view({"post": "create"}),
                name="create_apns_device",
            ),
            re_path(
                r"push-notifications/gcm",
                GCMDeviceAuthorizedViewSet.as_view({"post": "create"}),
                name="create_gcm_device",
            ),
            re_path(
                r"push-notifications/wns",
                WNSDeviceAuthorizedViewSet.as_view({"post": "create"}),
                name="create_wns_device",
            ),
            re_path(
                r"push-notifications/web",
                WebPushDeviceAuthorizedViewSet.as_view({"post": "create"}),
                name="create_web_device",
            ),
        ]
