from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_notifications"
    label = "baseapp_notifications"
    verbose_name = "BaseApp Notifications"
    default_auto_field = "django.db.models.AutoField"

    def ready(self) -> None:
        super().ready()

        # django-notifications-community connects its ``notify_handler`` in the library
        # app's ``AppConfig.ready()``. That app is intentionally not in INSTALLED_APPS here
        # (its "notifications" label is taken by the project's concrete notifications app),
        # so we connect the handler ourselves. The shared dispatch_uid keeps this idempotent
        # if the library app ever is installed alongside us.
        from notifications.base.models import notify_handler
        from notifications.signals import notify

        notify.connect(notify_handler, dispatch_uid="notifications.models.notification")

    def register_shared_services(self, registry):
        from .services import NotificationService

        registry.register(NotificationService())

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_notifications_interface

        registry.register("NotificationsInterface", get_notifications_interface)
