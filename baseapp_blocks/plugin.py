from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class BlocksPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_blocks"

    @property
    def package_name(self) -> str:
        return "baseapp_blocks"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_blocks": [
                    "baseapp_blocks.permissions.BlocksPermissionsBackend",
                ],
            },
            graphql_mutations=[
                "baseapp_blocks.graphql.mutations.BlocksMutations",
            ],
            required_packages=[
                {
                    "baseapp_profiles": "Block.actor / Block.target are Profile FKs and BlocksInterface resolvers disambiguate by the current Profile."
                },
            ],
            optional_packages=[],
        )
