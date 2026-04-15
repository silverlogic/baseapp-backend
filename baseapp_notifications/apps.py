from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_notifications"
    label = "baseapp_notifications"
    verbose_name = "BaseApp Notifications"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry):
        from .services import NotificationService

        registry.register(NotificationService())

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_notifications_interface

        registry.register("NotificationsInterface", get_notifications_interface)
