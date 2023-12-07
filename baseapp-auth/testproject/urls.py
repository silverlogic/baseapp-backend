import baseapp_auth.rest_framework.urls.auth_authtoken as auth_authtoken_urls
import baseapp_auth.rest_framework.urls.auth_jwt as auth_jwt_urls
import baseapp_auth.rest_framework.urls.auth_mfa as auth_mfa_urls
import baseapp_auth.rest_framework.urls.auth_mfa_jwt as auth_mfa_jwt_urls
import baseapp_auth.rest_framework.urls.pre_auth as pre_auth_urls
from baseapp_auth.rest_framework.routers.account import account_router
from django.contrib import admin
from django.urls import include, re_path

__all__ = [
    "urlpatterns",
]

v1_urlpatterns = [
    re_path(r"", include(account_router.urls)),
    re_path(r"auth/authtoken/", include(auth_authtoken_urls)),
    re_path(r"auth/jwt/", include(auth_jwt_urls)),
    re_path(r"auth/mfa/", include(auth_mfa_urls)),
    re_path(r"auth/mfa/jwt/", include(auth_mfa_jwt_urls)),
    re_path(r"auth/pre-auth/", include(pre_auth_urls)),
]

urlpatterns = [
    re_path(r"^admin/", admin.site.urls),
    re_path(r"v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
]
