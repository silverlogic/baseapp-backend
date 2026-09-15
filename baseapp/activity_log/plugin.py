from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ActivityLogPlugin(BaseAppPlugin):
    """
    The Activity Log plugin is used to log activities of users.
    """

    @property
    def name(self) -> str:
        return "baseapp_activity_log"

    @property
    def package_name(self) -> str:
        return "baseapp.activity_log"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            AUTHENTICATION_BACKENDS={
                "baseapp.activity_log": [
                    "baseapp.activity_log.permissions.ActivityLogPermissionsBackend",
                ],
            },
            django_extra_settings={},
            # GraphQL
            graphql_queries=[
                "baseapp.activity_log.graphql.queries.ActivityLogQueries",
            ],
            # Plugin deps
            required_packages=[],
            optional_packages=[],
        )
