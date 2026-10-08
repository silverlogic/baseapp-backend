from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class FilesPlugin(BaseAppPlugin):
    """
    The Files plugin provides file uploads, file management, and the ability to attach
    files to any object exposing a ``DocumentId`` (via ``FilesInterface``).
    """

    @property
    def name(self) -> str:
        return "baseapp_files"

    @property
    def package_name(self) -> str:
        return "baseapp.files"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[],
            AUTHENTICATION_BACKENDS={
                "baseapp_files": [
                    "baseapp.files.permissions.FilesPermissionsBackend",
                ],
            },
            graphql_queries=[
                "baseapp.files.graphql.queries.FilesQueries",
            ],
            graphql_mutations=[
                "baseapp.files.graphql.mutations.FilesMutations",
            ],
            v1_urlpatterns=self.v1_urlpatterns,
            required_packages=[
                {"baseapp_core": "Core shared models (DocumentId) and plugin infrastructure"},
            ],
            optional_packages=[
                {
                    "baseapp_profiles": "If enabled, File exposes the authoring Profile via the `profile` field."
                },
                {
                    "baseapp_comments": "If enabled, files expose comments through the CommentsInterface."
                },
                {
                    "baseapp_reactions": "If enabled, files expose reactions through the ReactionsInterface."
                },
            ],
        )

    def v1_urlpatterns(self, include, path, re_path):
        from baseapp.files.rest_framework.routers import files_router

        return [
            re_path(r"", include(files_router.urls)),
        ]
