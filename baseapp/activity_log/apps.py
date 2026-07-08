from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, GraphQLContributor, ServicesContributor):
    default = True
    name = "baseapp.activity_log"
    label = "baseapp_activity_log"
    verbose_name = "BaseApp Activity Log"
    default_auto_field = "django.db.models.BigAutoField"

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.shared_interfaces import (
            get_node_activity_log_interface,
            get_profile_activity_log_interface,
            get_user_activity_log_interface,
        )

        registry.register("NodeActivityLogInterface", get_node_activity_log_interface)
        registry.register("UserActivityLogInterface", get_user_activity_log_interface)
        registry.register("ProfileActivityLogInterface", get_profile_activity_log_interface)

    def register_shared_services(self, registry):
        from .services import ActivityLogService

        registry.register(ActivityLogService())
