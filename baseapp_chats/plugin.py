from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ChatsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_chats"

    @property
    def package_name(self) -> str:
        return "baseapp_chats"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_chats": [
                    "baseapp_chats.permissions.ChatsPermissionsBackend",
                ],
            },
            django_extra_settings={},
            graphql_queries=[
                "baseapp_chats.graphql.queries.ChatsQueries",
            ],
            graphql_mutations=[
                "baseapp_chats.graphql.mutations.ChatsMutations",
            ],
            graphql_subscriptions=[
                "baseapp_chats.graphql.subscriptions.ChatsSubscriptions",
            ],
            required_packages=[
                {"baseapp_profiles": "Chat participants and message authors are Profile FKs."},
            ],
            optional_packages=[
                {"baseapp_notifications": "Push/email notifications on new messages."},
                {"baseapp_mentions": "@-mentions inside message content."},
                {
                    "baseapp_blocks": "When installed, blocked profiles can't start/join "
                    "chats or message each other (via the blocks.lookup service)."
                },
            ],
        )
