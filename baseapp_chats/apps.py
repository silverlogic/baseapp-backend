from baseapp_core.plugins import BaseAppConfig, GraphQLContributor, ServicesContributor


class PackageConfig(BaseAppConfig, ServicesContributor, GraphQLContributor):
    default = True
    name = "baseapp_chats"
    label = "baseapp_chats"
    verbose_name = "BaseApp Chats"
    default_auto_field = "django.db.models.BigAutoField"

    def register_shared_services(self, registry):
        from .services import ChatsParticipationService

        registry.register(ChatsParticipationService())

    def register_graphql_shared_interfaces(self, registry):
        from .graphql.shared_interfaces import get_chat_rooms_interface

        registry.register("ChatRoomsInterface", get_chat_rooms_interface)
