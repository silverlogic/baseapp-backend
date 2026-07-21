from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class GeoPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_geo"

    @property
    def package_name(self) -> str:
        return "baseapp_geo"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_geo": [
                    "baseapp_geo.permissions.GeoPermissionsBackend",
                ],
            },
            # Graphql
            graphql_queries=[
                "baseapp_geo.graphql.queries.GeoQueries",
            ],
            graphql_mutations=[
                "baseapp_geo.graphql.mutations.GeoMutations",
            ],
            # Deps
            required_packages=[],
            optional_packages=[],
        )
