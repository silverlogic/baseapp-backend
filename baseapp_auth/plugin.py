"""
Plugin definition for baseapp_auth (settings only).

Contributes urlpatterns as a string module path so the registry and Django
load the URLconf at resolve time; plugin.py never imports views or urls.
"""

from typing import TYPE_CHECKING

from django.apps import apps

from baseapp_core.plugins.base import BaseAppPlugin, PackageSettings

if TYPE_CHECKING:
    from django.urls import URLResolver


class AuthPlugin(BaseAppPlugin):
    @property
    def name(self) -> str:
        return "baseapp_auth"

    @property
    def package_name(self) -> str:
        return "baseapp_auth"

    def get_settings(self) -> PackageSettings:
        return PackageSettings(
            INSTALLED_APPS=[
                "django.contrib.sites",
                "allauth",
                "allauth.account",
                "allauth.headless",
            ],
            MIDDLEWARE={
                "baseapp_auth": ["allauth.account.middleware.AccountMiddleware"],
            },
            AUTHENTICATION_BACKENDS={
                "baseapp_auth": ["allauth.account.auth_backends.AuthenticationBackend"],
            },
            required_packages=["baseapp_core"],
            urlpatterns=self.urlpatterns,
            v1_urlpatterns=self.v1_urlpatterns,
        )

    @staticmethod
    def urlpatterns(include, path, re_path) -> "list[URLResolver]":
        """Root-level allauth routes (``accounts/`` and admin redirects), when allauth is installed."""
        if not apps.is_installed("allauth"):
            return []
        from baseapp_auth.allauth.urls import allauth_admin_urls

        return [path("", include(allauth_admin_urls))]

    @staticmethod
    def v1_urlpatterns(include, path, re_path) -> "list[URLResolver]":
        from baseapp_auth.allauth.urls import allauth_headless_urls
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
            *(
                [re_path(r"", include(allauth_headless_urls))]
                if apps.is_installed("allauth.headless")
                else []
            ),
        ]
