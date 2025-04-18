import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node

ContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)
ContentPostObjectType = ContentPost.get_graphql_object_type()


class ContentFeedQueries:
    content_post = Node.Field(ContentPostObjectType)
    content_posts = DjangoFilterConnectionField(ContentPostObjectType)
