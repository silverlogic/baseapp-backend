from baseapp_core.graphql import DjangoObjectType
from graphene import relay

from baseapp.content_feed.graphql.filters import ContentPostFilter
from baseapp.content_feed.models import SwappedContentPost as ContentPost


class ContentPostObjectType(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node,)
        model = ContentPost
        fields = ("pk", "user", "profile", "content")
        filterset_class = ContentPostFilter
