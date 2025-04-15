import swapper
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

from baseapp.content_feed.graphql.filters import (
    ContentPostFilter,
    ContentPostImageFilter,
)
from baseapp_core.graphql import DjangoObjectType

ContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)

ContentPostImage = swapper.load_model(
    "baseapp_content_feed", "ContentPostImage", required=False, require_ready=False
)


class ContentPostImageObjectType(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node,)
        model = ContentPostImage
        fields = ("pk", "post", "image")
        filterset_class = ContentPostImageFilter


class ContentPostObjectType(DjangoObjectType):
    images = DjangoFilterConnectionField(lambda: ContentPostImageObjectType)

    class Meta:
        interfaces = (relay.Node,)
        model = ContentPost
        fields = ("pk", "user", "profile", "content", "images")
        filterset_class = ContentPostFilter

    def resolve_images(self, info, **kwargs):
        return ContentPostImage.objects.filter(post=self.pk)
