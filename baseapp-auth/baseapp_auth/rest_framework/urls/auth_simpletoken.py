from baseapp_core.rest_framework.routers import DefaultRouter
from django.urls import include, re_path

simpletoken_router = DefaultRouter(trailing_slash=False)

# Login
from baseapp_auth.rest_framework.login.views import LoginViewSet  # noqa

simpletoken_router.register(r"login", LoginViewSet, basename="login")

__all__ = [
    "urlpatterns",
]

urlpatterns = [re_path(r"/", include(simpletoken_router.urls))]
