from baseapp_core.plugins import (
    BaseAppConfig,
    GraphQLContributor,
    SerializersContributor,
    ServicesContributor,
)
from baseapp_core.plugins.shared_graphql_interfaces import (
    GraphQLSharedInterfaceRegistry,
)
from baseapp_core.plugins.shared_serializers import SharedSerializerRegistry
from baseapp_core.plugins.shared_services import SharedServiceRegistry


class PackageConfig(
    BaseAppConfig,
    ServicesContributor,
    SerializersContributor,
    GraphQLContributor,
):
    default = True
    name = "baseapp_profiles"
    label = "baseapp_profiles"
    verbose_name = "BaseApp Profiles"
    default_auto_field = "django.db.models.AutoField"

    def register_shared_services(self, registry: SharedServiceRegistry) -> None:
        from .services import GraphQLProfileService

        registry.register(GraphQLProfileService())

    def register_shared_serializers(self, registry: SharedSerializerRegistry) -> None:
        from .rest_framework.serializers import JWTProfileSerializer

        registry.register("profiles.jwt_profile", JWTProfileSerializer)

    def register_graphql_shared_interfaces(self, registry: GraphQLSharedInterfaceRegistry) -> None:
        from .graphql.interfaces import (
            get_profile_interface,
            get_profiles_list_interface,
        )

        registry.register("ProfileInterface", get_profile_interface)
        registry.register("ProfilesInterface", get_profiles_list_interface)
