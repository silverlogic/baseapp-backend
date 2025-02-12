from django.contrib import admin
from django.urls import include, path

from baseapp_core.graphql import GraphQLView

__all__ = [
    "urlpatterns",
]

v1_urlpatterns = [
    path(r"", include("baseapp_url_shortening.urls")),
]

urlpatterns = [
    path("graphql", GraphQLView.as_view(graphiql=True)),
    path("admin/", admin.site.urls),
    path("v1/", include((v1_urlpatterns, "v1"), namespace="v1")),
]
