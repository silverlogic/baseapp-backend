from django.contrib import admin
from django.urls import include, path, re_path

import baseapp_auth.rest_framework.urls.auth_authtoken as auth_authtoken_urls
import baseapp_auth.rest_framework.urls.auth_jwt as auth_jwt_urls
import baseapp_auth.rest_framework.urls.auth_mfa as auth_mfa_urls
import baseapp_auth.rest_framework.urls.auth_mfa_jwt as auth_mfa_jwt_urls
import baseapp_auth.rest_framework.urls.pre_auth as pre_auth_urls
import baseapp_wagtail.urls as baseapp_wagtail_urls
from baseapp_auth.allauth.urls import allauth_admin_urls, allauth_headless_urls
from baseapp_auth.rest_framework.routers.account import (
    account_router,
    users_router_nested,
)
from baseapp_core.graphql import GraphQLView
from baseapp_core.rest_framework.routers import DefaultRouter
from baseapp_e2e.rest_framework.views import E2EViewSet
from baseapp_payments.router import payments_router

__all__ = [
    "urlpatterns",
]

v1_urlpatterns = [
    path(r"", include("baseapp_url_shortening.urls")),
    re_path(r"", include(account_router.urls)),
    re_path(r"", include(users_router_nested.urls)),
    re_path(r"auth/authtoken/", include(auth_authtoken_urls)),
    re_path(r"auth/jwt/", include(auth_jwt_urls)),
    re_path(r"auth/mfa/", include(auth_mfa_urls)),
    re_path(r"auth/mfa/jwt/", include(auth_mfa_jwt_urls)),
    re_path(r"auth/pre-auth/", include(pre_auth_urls)),
    re_path(r"payments/", include(payments_router.urls)),
    re_path(r"", include(allauth_headless_urls)),
]

router = DefaultRouter(trailing_slash=False)
router.register(r"e2e", E2EViewSet, basename="e2e")

urlpatterns = [
    path("graphql", GraphQLView.as_view(graphiql=True)),
    path("admin/", admin.site.urls),
    path("v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
    path("", include(allauth_admin_urls)),
    path("", include(baseapp_wagtail_urls)),
    path("", include(router.urls)),
]
