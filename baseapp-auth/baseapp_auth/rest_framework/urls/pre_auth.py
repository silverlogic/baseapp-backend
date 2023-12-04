from baseapp_core.rest_framework.routers import DefaultRouter
from django.urls import include, re_path

pre_auth_router = DefaultRouter(trailing_slash=False)

# Pre Auth
from baseapp_auth.rest_framework.pre_auth.views import PreAuthViewSet  # noqa

pre_auth_router.register(r"", PreAuthViewSet, basename="pre_auth")

__all__ = [
    "urlpatterns",
]

urlpatterns = [re_path(r"", include(pre_auth_router.urls))]
