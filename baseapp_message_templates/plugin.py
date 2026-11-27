from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class MessageTemplatesPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_message_templates"

    @property
    def package_name(self) -> str:
        return "baseapp_message_templates"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            AUTHENTICATION_BACKENDS={
                "baseapp_message_templates": [
                    "baseapp_message_templates.permissions.MessageTemplatesPermissionsBackend",
                ],
            },
            # GraphQL
            graphql_queries=[
                "baseapp_message_templates.graphql.queries.MessageTemplatesQueries",
            ],
            graphql_mutations=[
                "baseapp_message_templates.graphql.mutations.MessageTemplatesMutations",
            ],
            required_packages=[],
            optional_packages=[],
        )
