from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class ImpersonationPlugin(BaseAppPlugin):
    """
    Lets an authorized user act as another user for a limited time, with a reason, through
    tokens that every request checks against an `ImpersonationSession`.
    """

    @property
    def name(self) -> str:
        return "baseapp_impersonation"

    @property
    def package_name(self) -> str:
        return "baseapp_auth.impersonation"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            MIDDLEWARE={
                "baseapp_impersonation": [
                    "baseapp_auth.impersonation.middleware.ImpersonationMiddleware",
                ],
            },
            GRAPHENE__MIDDLEWARE={
                "baseapp_impersonation": [
                    "baseapp_auth.impersonation.graphql.middleware.ImpersonationReadOnlyMiddleware",
                ],
            },
            AUTHENTICATION_BACKENDS={
                "baseapp_impersonation": [
                    "baseapp_auth.impersonation.permissions.ImpersonationPermissionsBackend",
                ],
            },
            graphql_mutations=[
                "baseapp_auth.impersonation.graphql.mutations.ImpersonationMutations",
            ],
            django_extra_settings={
                "BASEAPP_AUTH_IMPERSONATION_TTL": 60 * 60,
                "BASEAPP_AUTH_IMPERSONATION_READ_ONLY": True,
                "BASEAPP_AUTH_IMPERSONATION_CAN_IMPERSONATE": (
                    "baseapp_auth.impersonation.permissions.default_can_impersonate"
                ),
                "BASEAPP_AUTH_IMPERSONATION_TOKEN_HOOK": None,
                "BASEAPP_AUTH_IMPERSONATION_READ_ONLY_ALLOWLIST": (),
                "BASEAPP_AUTH_IMPERSONATION_DENYLIST": (
                    r"^/v1/users/change-password",
                    r"^/v1/users/delete-account",
                    r"^/v1/change-email",
                    r"^/v1/auth/mfa/",
                ),
                "BASEAPP_AUTH_IMPERSONATION_DENIED_PERMISSIONS": (),
                "BASEAPP_AUTH_IMPERSONATION_CACHE_TIMEOUT": 30,
            },
            required_packages=[
                {"baseapp_core": "Plugin infrastructure and the GraphQL base types"},
                {"baseapp_auth": "JWT login, whose claims the session tokens reuse"},
            ],
        )
