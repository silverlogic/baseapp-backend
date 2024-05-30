from django.urls import include, re_path

from baseapp_core.rest_framework.routers import DefaultRouter

authtoken_router = DefaultRouter(trailing_slash=False)

# Login
from baseapp_auth.rest_framework.login.views import AuthTokenViewSet  # noqa

authtoken_router.register(r"login", AuthTokenViewSet, basename="login")

__all__ = [
    "urlpatterns",
]

urlpatterns = [re_path(r"", include(authtoken_router.urls))]
