import swapper
from baseapp_core.graphql import DjangoObjectType
from graphene import relay

from baseapp.content_feed.graphql.filters import ContentPostFilter

ContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)

class ContentPostObjectType(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node,)
        model = ContentPost
        fields = ("pk", "user", "profile", "content")
        filterset_class = ContentPostFilter
