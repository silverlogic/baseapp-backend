import baseapp_auth.rest_framework.urls.auth_jwt as auth_jwt_urls
import baseapp_auth.rest_framework.urls.pre_auth as pre_auth_urls
from baseapp_auth.rest_framework.routers.account import (
    account_router,
    users_router_nested,
)
from baseapp_core.graphql import GraphQLView
from django.contrib import admin
from django.urls import include, re_path

from django.shortcuts import render


def user_agent_test_view(request):
    return render(request, "test.html", {"user_agent": request.user_agent})


__all__ = [
    "urlpatterns",
]

v1_urlpatterns = [
    re_path(r"", include(account_router.urls)),
    re_path(r"", include(users_router_nested.urls)),
    re_path(r"auth/jwt/", include(auth_jwt_urls)),
    re_path(r"auth/pre-auth/", include(pre_auth_urls)),
    re_path("_allauth/v1/", include("allauth.headless.urls")),
]

urlpatterns = [
    re_path(r"^admin/", admin.site.urls),
    re_path(r"^user-agents/", user_agent_test_view, name="user_agent_test"),
    re_path(r"v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
    re_path(r"graphql", GraphQLView.as_view(graphiql=True)),
]
