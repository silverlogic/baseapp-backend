from baseapp_core.rest_framework.routers import DefaultRouter
from django.urls import include, re_path

jwt_router = DefaultRouter(trailing_slash=False)

# Login
from baseapp_auth.rest_framework.jwt.views import JWTAuthViewSet  # noqa

jwt_router.register(r"", JWTAuthViewSet, basename="jwt")

__all__ = [
    "urlpatterns",
]

urlpatterns = [re_path(r"", include(jwt_router.urls))]
