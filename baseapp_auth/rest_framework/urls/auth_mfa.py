from django.urls import include, re_path

import baseapp_auth.rest_framework.urls.mfa as mfa_urls
from baseapp_core.rest_framework.routers import DefaultRouter

mfa_login_router = DefaultRouter(trailing_slash=False)

# Login
from baseapp_auth.rest_framework.login.views import MfaAuthTokenViewSet  # noqa

mfa_login_router.register(r"login", MfaAuthTokenViewSet, basename="login")

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    re_path(r"", include(mfa_login_router.urls)),  # MFA login
    re_path(r"", include(mfa_urls)),  # other MFA endpoints
]
