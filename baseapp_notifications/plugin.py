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
            INSTALLED_APPS=[
                "push_notifications",
            ],
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
            optional_packages=[],
        )
