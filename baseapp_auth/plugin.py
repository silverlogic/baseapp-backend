"""
Plugin definition for baseapp_auth (settings only).

Contributes urlpatterns as a string module path so the registry and Django
load the URLconf at resolve time; plugin.py never imports views or urls.
"""

from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings


class AuthPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_auth"

    @property
    def package_name(self) -> str:
        return "baseapp_auth"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            required_packages=["baseapp_core"],
            v1_urlpatterns=self.v1_urlpatterns,
        )

    @staticmethod
    def v1_urlpatterns(include, path, re_path):
        from baseapp_auth.rest_framework.routers.account import (
            account_router,
            users_router_nested,
        )

        return [
            re_path(r"", include(account_router.urls)),
            re_path(r"", include(users_router_nested.urls)),
            re_path(r"auth/authtoken/", include("baseapp_auth.rest_framework.urls.auth_authtoken")),
            re_path(r"auth/jwt/", include("baseapp_auth.rest_framework.urls.auth_jwt")),
            re_path(r"auth/mfa/", include("baseapp_auth.rest_framework.urls.auth_mfa")),
            re_path(r"auth/mfa/jwt/", include("baseapp_auth.rest_framework.urls.auth_mfa_jwt")),
            re_path(r"auth/pre-auth/", include("baseapp_auth.rest_framework.urls.pre_auth")),
        ]
