from baseapp_content_feed.graphql.filters import ContentPostFilter
from baseapp_core.graphql import DjangoObjectType
from baseapp_content_feed.models import SwappedContentPost as ContentPost
from graphene import relay


class ContentPostObjectType(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node,)
        model = ContentPost
        fields = (
            "pk",
            "author",
            "content"
        )
        filterset_class = ContentPostFilter
