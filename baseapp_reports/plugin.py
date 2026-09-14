from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ReportsPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_reports"

    @property
    def package_name(self) -> str:
        return "baseapp_reports"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_reports": [
                    "baseapp_reports.permissions.ReportsPermissionsBackend",
                ],
            },
            # GraphQL
            graphql_queries=[
                "baseapp_reports.graphql.queries.ReportsQueries",
            ],
            graphql_mutations=[
                "baseapp_reports.graphql.mutations.ReportsMutations",
            ],
            # Deps
            required_packages=[],
            optional_packages=[
                {
                    "baseapp_profiles": "If enabled, reports use the current Profile to detect self-reports."
                },
            ],
        )
