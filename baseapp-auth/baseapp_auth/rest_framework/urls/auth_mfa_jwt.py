from baseapp_core.rest_framework.routers import DefaultRouter
from django.urls import include, re_path

mfa_jwt_login_router = DefaultRouter(trailing_slash=False)

# Login
from baseapp_auth.rest_framework.login.views import MfaJwtViewSet  # noqa

mfa_jwt_login_router.register(r"login", MfaJwtViewSet, basename="login")

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    re_path(r"", include(mfa_jwt_login_router.urls)),  # MFA JWT login
]
