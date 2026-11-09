import strawberry
import swapper

from baseapp_core.strawberry import CountedConnection, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.relay import typed_node_field

from ..filters import ContentPostFilter

ContentPost = swapper.load_model("baseapp_content_feed", "ContentPost")
ContentPostLazyType = type_for_model(ContentPost)


@strawberry.type
class ContentFeedQueries:
    content_post = typed_node_field(ContentPostLazyType)
    content_posts = connection(
        CountedConnection[ContentPostLazyType] | None, filterset_class=ContentPostFilter
    )
