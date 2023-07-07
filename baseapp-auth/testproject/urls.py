from django.conf.urls import include, re_path
from django.contrib import admin

# from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from baseapp_auth.rest_framework.router import router as v1_router

urlpatterns = [
    re_path(r"^admin/", admin.site.urls),
    re_path(r"v1/auth/", include((v1_router.urls, "v1"), namespace="v1")),
    re_path(r"v1/auth/", include("trench.urls")),
    re_path(r"v1/auth/jwt/", include("trench.urls.jwt")),
    # re_path(r"v1/auth/jwt", TokenObtainPairView.as_view(), name="jwt"),
    # re_path(r"v1/auth/jwt/refresh", TokenRefreshView.as_view(), name="jwt-token-refresh"),
    # TODO: restructure urls paths to demo simple_token, jwt, mfa together:
    # TODO: paths to use: /auth, /auth/jwt, /auth/mfa, /auth/mfa/jwt
]
