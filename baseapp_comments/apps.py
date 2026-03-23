from baseapp_core.plugins import BaseAppConfig, GraphQLContributor


class PackageConfig(BaseAppConfig, GraphQLContributor):
    default = True
    name = "baseapp_comments"
    label = "baseapp_comments"
    verbose_name = "BaseApp Comments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        super().ready()
        import baseapp_comments.signals  # noqa: F401

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.interfaces import get_comments_interface

        registry.register("CommentsInterface", get_comments_interface)
