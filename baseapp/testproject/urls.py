from django.contrib import admin
from django.urls import include, path

import baseapp_wagtail.urls as baseapp_wagtail_urls
from baseapp_core.graphql import GraphQLView
from baseapp_core.rest_framework.routers import DefaultRouter
from baseapp_e2e.rest_framework.views import E2EViewSet

__all__ = [
    "urlpatterns",
]

v1_urlpatterns = [
    path(r"", include("baseapp_url_shortening.urls")),
]

router = DefaultRouter(trailing_slash=False)
router.register(r"e2e", E2EViewSet, basename="e2e")

urlpatterns = [
    path("graphql", GraphQLView.as_view(graphiql=True)),
    path("admin/", admin.site.urls),
    path("v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
    path("", include(baseapp_wagtail_urls)),
    path("", include(router.urls)),
]
