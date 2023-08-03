import testproject.urls.mfa as mfa_urls
from baseapp_auth.rest_framework.router import router as auth_router
from django.contrib import admin
from django.urls import include, re_path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    re_path(r"^admin/", admin.site.urls),
    re_path(
        r"v1/auth/", include((auth_router.urls, "v1"), namespace="v1")
    ),  # non-JWT auth; login endpoint uses MFA if configured for the user
    re_path(r"v1/auth/jwt", TokenObtainPairView.as_view(), name="jwt"),  # JWT auth
    re_path(
        r"v1/auth/jwt/refresh",
        TokenRefreshView.as_view(),
        name="jwt-token-refresh",
    ),  # JWT auth (token refresh)
    re_path(r"v1/auth/mfa", include(mfa_urls)),  # MFA endpoints
    re_path(r"v1/auth/mfa/jwt/", include("trench.urls.jwt")),
]
