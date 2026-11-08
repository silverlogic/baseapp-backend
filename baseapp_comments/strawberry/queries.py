from collections.abc import Iterable

import strawberry
import swapper
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.relay import typed_node_field

from .filters import CommentFilter
from .types import CommentLazyType

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label


@strawberry.type
class CommentsQueries:
    comment = typed_node_field(CommentLazyType)

    @connection(CountedConnection[CommentLazyType] | None, filterset_class=CommentFilter)
    def all_comments(self, info: Info) -> Iterable[Model]:
        if info.context.user.has_perm(f"{app_label}.view_all_comments"):
            return Comment.objects.all()
        return Comment.objects.none()
