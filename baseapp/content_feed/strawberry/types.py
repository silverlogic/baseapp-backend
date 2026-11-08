from collections.abc import Iterable

import strawberry
import strawberry_django
import swapper
from django.apps import apps
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import CountedConnection, Node, django_type, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.fields import thumbnail_field

from ..graphql.filters import ContentPostFilter, ContentPostImageFilter

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
ContentPostImage = swapper.load_model("baseapp_content_feed", "ContentPostImage")


@django_type(ContentPostImage, filterset_class=ContentPostImageFilter, relations=("post",))
class ContentPostImageType(Node):
    pk: int | None = strawberry_django.field()
    image: str | None = thumbnail_field("image")


@django_type(
    ContentPost,
    filterset_class=ContentPostFilter,
    relations=("user", "profile") if apps.is_installed("baseapp_profiles") else ("user",),
)
class ContentPostType(
    *strawberry_shared_interfaces.get(
        "MentionsInterface", "ReactionsInterface", "CommentsInterface"
    ),
    Node,
):
    created: strawberry.auto
    modified: strawberry.auto
    content: strawberry.auto
    pk: int | None = strawberry_django.field()

    @connection(
        CountedConnection[type_for_model(ContentPostImage)] | None,
        filterset_class=ContentPostImageFilter,
    )
    def images(self, info: Info) -> Iterable[Model]:
        return ContentPostImage.objects.filter(post=self.pk)
