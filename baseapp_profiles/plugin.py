from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings
from baseapp_profiles.conf import DEFAULTS as PROFILES_DEFAULTS


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
            django_extra_settings=dict(PROFILES_DEFAULTS),
            celery_beat_schedules={
                "baseapp_profiles_expire_invitations": {
                    "task": "baseapp_profiles.tasks.expire_invitations",
                    "schedule": 60 * 60,
                    # 75% of the interval, so a backed-up beat never runs duplicates.
                    "options": {"expires": 45 * 60},
                },
            },
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
