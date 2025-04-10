import swapper
from graphene_django.filter import DjangoFilterConnectionField

ContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)
ContentPostObjectType = ContentPost.get_graphql_object_type()


class ContentFeedQueries:
    content_posts = DjangoFilterConnectionField(ContentPostObjectType)
