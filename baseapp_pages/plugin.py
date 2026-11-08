from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class PagesPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_pages"

    @property
    def package_name(self) -> str:
        return "baseapp_pages"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            AUTHENTICATION_BACKENDS={
                "baseapp_pages": [
                    "baseapp_pages.permissions.PagesPermissionsBackend",
                ],
            },
            graphql_queries=[
                "baseapp_pages.graphql.queries.PagesQueries",
            ],
            graphql_mutations=[
                "baseapp_pages.graphql.mutations.PagesMutations",
            ],
            strawberry_queries=[
                "baseapp_pages.strawberry.queries.PagesQueries",
            ],
            strawberry_mutations=[
                "baseapp_pages.strawberry.mutations.PagesMutations",
            ],
            strawberry_types=[
                "baseapp_pages.strawberry.types.PageType",
            ],
            required_packages=[],
            optional_packages=[
                "baseapp_comments",
            ],
        )
