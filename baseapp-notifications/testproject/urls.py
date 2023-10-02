from django.urls import path
from graphene_django.views import GraphQLView

__all__ = [
    "urlpatterns",
]

urlpatterns = [
    path("graphql", GraphQLView.as_view(graphiql=True)),
]
