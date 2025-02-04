from django.contrib import admin
from django.urls import include, path

from baseapp_core.graphql import GraphQLView
import baseapp_wagtail.urls as baseapp_wagtail_urls


__all__ = [
    "urlpatterns",
]

urlpatterns = [
    path("graphql", GraphQLView.as_view(graphiql=True)),
    path("admin/", admin.site.urls),
    path("", include(baseapp_wagtail_urls))
]
