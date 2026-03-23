from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class OrganizationsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_organizations"

    @property
    def package_name(self) -> str:
        return "baseapp_organizations"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            AUTHENTICATION_BACKENDS={
                "baseapp_organizations": [
                    "baseapp_organizations.permissions.OrganizationsPermissionsBackend",
                ],
            },
            graphql_queries=[
                "baseapp_organizations.graphql.queries.OrganizationsQueries",
            ],
            graphql_mutations=[
                "baseapp_organizations.graphql.mutations.OrganizationsMutations",
            ],
            required_packages=[
                "baseapp_profiles",
            ],
            optional_packages=[],
        )
