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
            django_extra_settings={
                # STORAGES alias holding uploaded files. Point it at a private storage
                # (S3 with querystring_auth, or SignedFileSystemStorage) to make files
                # readable only through signed, expiring URLs.
                "BASEAPP_FILES_STORAGE": "default",
                "BASEAPP_FILES_ALLOW_ANONYMOUS_UPLOADS": False,
                "BASEAPP_FILES_UPLOAD_TOKEN_MAX_AGE": 24 * 60 * 60,
                # None: anonymous uploads share MAX_FILE_UPLOAD_SIZE.
                "BASEAPP_FILES_ANONYMOUS_MAX_FILE_SIZE": None,
                "BASEAPP_FILES_ANONYMOUS_UPLOAD_RATE": "20/hour",
                # Link lifetime for SignedFileSystemStorage; S3 uses its querystring_expire.
                "BASEAPP_FILES_SIGNED_URL_MAX_AGE": 60 * 60,
                "BASEAPP_FILES_UNCLAIMED_ANONYMOUS_MAX_AGE": 24 * 60 * 60,
            },
            celery_beat_schedules={
                "baseapp_files_cleanup_expired_uploads": {
                    "task": "baseapp.files.services.cleanup.cleanup_expired_uploads",
                    "schedule": 60 * 60,
                },
                "baseapp_files_cleanup_unclaimed_anonymous_files": {
                    "task": "baseapp.files.services.cleanup.cleanup_unclaimed_anonymous_files",
                    "schedule": 60 * 60,
                },
            },
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
