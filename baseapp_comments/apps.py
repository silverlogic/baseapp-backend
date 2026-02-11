from baseapp_core.app_config import (
    BaseAppConfig,
    GraphQLContributor,
    ServicesContributor,
)


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_comments"
    label = "baseapp_comments"
    verbose_name = "BaseApp Comments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        super().ready()
        import baseapp_comments.signals  # noqa: F401

    def register_shared_services(self, registry):
        from .services import CommentsCountService

        registry.register("comments_count", CommentsCountService())

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_comments_shared_interface

        registry.register("comments", get_comments_shared_interface)
