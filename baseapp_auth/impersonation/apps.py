from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import BaseAppConfig, GraphQLContributor


class PackageConfig(BaseAppConfig, GraphQLContributor):
    default = True
    name = "baseapp_auth.impersonation"
    label = "baseapp_impersonation"
    verbose_name = _("BaseApp Impersonation")
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        super().ready()
        from . import checks  # noqa: F401  (registers the wiring checks)

    def register_graphql_shared_interfaces(self, registry) -> None:
        from .graphql.interfaces import get_impersonation_interface

        registry.register("ImpersonationInterface", get_impersonation_interface)
