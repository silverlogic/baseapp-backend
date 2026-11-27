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
                # Parts directory for storages without a local path (None: system temp).
                "BASEAPP_FILES_UPLOAD_TEMP_DIR": None,
                # Protected downloads (baseapp.files.downloads): lifetime of a download
                # link, an optional callable(user, request) -> bool vetoing its use, and
                # where baseapp.files.downloads.urls is mounted.
                "BASEAPP_FILES_DOWNLOAD_TICKET_MAX_AGE": 300,
                "BASEAPP_FILES_DOWNLOAD_TICKET_USER_CHECK": None,
                "BASEAPP_FILES_PROTECTED_DOWNLOADS_URL": "/v1/files/protected/",
            },
            celery_beat_schedules={
                "baseapp_files_cleanup_expired_uploads": {
                    "task": "baseapp.files.services.cleanup.cleanup_expired_uploads",
                    "schedule": 60 * 60,
                    # 75% of the interval, so a backed-up beat never runs duplicates.
                    "options": {"expires": 45 * 60},
                },
                "baseapp_files_cleanup_unclaimed_anonymous_files": {
                    "task": "baseapp.files.services.cleanup.cleanup_unclaimed_anonymous_files",
                    "schedule": 60 * 60,
                    # 75% of the interval, so a backed-up beat never runs duplicates.
                    "options": {"expires": 45 * 60},
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
            # Before the router: its `files/{pk}` routes would otherwise see "protected".
            re_path(r"^files/protected/", include("baseapp.files.downloads.urls")),
            re_path(r"", include(files_router.urls)),
        ]
