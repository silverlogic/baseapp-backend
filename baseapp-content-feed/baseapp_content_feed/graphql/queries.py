from baseapp_core.graphql import Node
from graphene_django.filter import DjangoFilterConnectionField

from .object_types import ContentPostObjectType


class ContentFeedQueries:
    content_posts = DjangoFilterConnectionField(ContentPostObjectType)
