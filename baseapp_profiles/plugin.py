from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ProfilesPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_profiles"

    @property
    def package_name(self) -> str:
        return "baseapp_profiles"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            MIDDLEWARE={
                "baseapp_profiles": [
                    "baseapp_profiles.middleware.CurrentProfileMiddleware",
                ],
            },
            GRAPHENE__MIDDLEWARE={
                "baseapp_profiles": [
                    "baseapp_profiles.graphql.middleware.CurrentProfileMiddleware",
                ],
            },
            AUTHENTICATION_BACKENDS={
                "baseapp_profiles": [
                    "baseapp_profiles.permissions.ProfilesPermissionsBackend",
                ],
            },
            graphql_queries=[
                "baseapp_profiles.graphql.queries.ProfilesQueries",
            ],
            graphql_mutations=[
                "baseapp_profiles.graphql.mutations.ProfilesMutations",
            ],
            required_packages=[],
            optional_packages=[
                "baseapp_blocks",
                "baseapp_follows",
                "baseapp_reports",
                "baseapp_comments",
                "baseapp_pages",
                "baseapp.activity_log",
                "baseapp_chats",
            ],
        )
