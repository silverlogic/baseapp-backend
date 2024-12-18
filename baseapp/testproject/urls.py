from baseapp_core.graphql import GraphQLView
from django.contrib import admin
from django.urls import path

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    path("graphql", GraphQLView.as_view(graphiql=True)),
    path("admin/", admin.site.urls),
]
