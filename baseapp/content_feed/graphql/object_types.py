import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp.content_feed.graphql.filters import (
    ContentPostFilter,
    ContentPostImageFilter,
)
from baseapp_core.graphql import DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql.fields import ThumbnailField
from baseapp_reactions.graphql.object_types import ReactionsInterface

ContentPost = swapper.load_model(
    "baseapp_content_feed", "ContentPost", required=False, require_ready=False
)

ContentPostImage = swapper.load_model(
    "baseapp_content_feed", "ContentPostImage", required=False, require_ready=False
)


class ContentPostImageObjectType(DjangoObjectType):
    image = ThumbnailField(required=False)

    class Meta:
        interfaces = (RelayNode,)
        model = ContentPostImage
        fields = ("pk", "post", "image")
        filterset_class = ContentPostImageFilter


class ContentPostObjectType(DjangoObjectType):
    images = DjangoFilterConnectionField(lambda: ContentPostImageObjectType)

    class Meta:
        interfaces = (
            RelayNode,
            ReactionsInterface,
        )
        model = ContentPost
        fields = (
            "pk",
            "user",
            "profile",
            "content",
            "images",
            "created",
            "modified",
            "is_reactions_enabled",
        )
        filterset_class = ContentPostFilter

    def resolve_images(self, info, **kwargs):
        return ContentPostImage.objects.filter(post=self.pk)
