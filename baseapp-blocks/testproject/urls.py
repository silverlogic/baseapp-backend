from django.urls import path

from baseapp_core.graphql import GraphQLView

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    path("graphql", GraphQLView.as_view(graphiql=True)),
]
