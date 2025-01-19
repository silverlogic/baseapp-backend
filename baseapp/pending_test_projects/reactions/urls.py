from baseapp_core.graphql import GraphQLView
from django.contrib import admin
from django.urls import path

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("graphql", GraphQLView.as_view(graphiql=True)),
]
