from django.utils.translation import gettext_lazy as _

from baseapp_core.plugins import (
    BaseAppConfig,
    GraphQLContributor,
    GraphQLSharedInterfaceRegistry,
    ServicesContributor,
)


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_follows"
    label = "baseapp_follows"
    verbose_name = _("BaseApp Follows")
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry) -> None:
        from .services import FollowableMetadataService

        registry.register(FollowableMetadataService())

    def register_strawberry_shared_interfaces(
        self, registry: GraphQLSharedInterfaceRegistry
    ) -> None:
        from .strawberry import get_follows_interface

        registry.register("FollowsInterface", get_follows_interface)
