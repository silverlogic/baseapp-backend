from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_comments"
    label = "baseapp_comments"
    verbose_name = "BaseApp Comments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        super().ready()
        import baseapp_comments.signals  # noqa: F401

    def register_shared_services(self, registry) -> None:
        from .services import CommentableMetadataService

        registry.register(CommentableMetadataService())

    def register_graphql_shared_interfaces(self, registry) -> None:
        from .graphql.interfaces import get_comments_interface

        registry.register("CommentsInterface", get_comments_interface)
