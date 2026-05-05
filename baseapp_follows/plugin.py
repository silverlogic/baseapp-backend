from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class FollowsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_follows"

    @property
    def package_name(self) -> str:
        return "baseapp_follows"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_follows": [
                    "baseapp_follows.permissions.FollowsPermissionsBackend",
                ],
            },
            # GraphQL
            graphql_mutations=[
                "baseapp_follows.graphql.mutations.FollowsMutations",
            ],
            # Deps
            required_packages=[],
            optional_packages=[
                {
                    "baseapp_profiles": "If enabled, follows will use the Profile model to identify the actor."
                },
            ],
        )
