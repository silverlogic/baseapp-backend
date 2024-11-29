from baseapp_core.graphql import DjangoObjectType
from graphene import relay
from graphene import List

from baseapp_content_feed.graphql.filters import ContentPostFilter
from baseapp_content_feed.models import SwappedContentPost as ContentPost
from baseapp_content_feed.models import SwappedContentPostImage as ContentPostImage


class ContentPostObjectType(DjangoObjectType):
    content_images = List(lambda: ContentPostImageObjectType)


    def resolve_content_images(self, info):
        return ContentPostImage.objects.filter(post=self)


    class Meta:
        interfaces = (relay.Node,)
        model = ContentPost
        fields = ("pk", "author", "content", "content_images")
        filterset_class = ContentPostFilter


class ContentPostImageObjectType(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node,)
        model = ContentPostImage
        fields = ("pk", "image", "post")