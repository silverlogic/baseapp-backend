import swapper
from baseapp_core.graphql import Node
from graphene_django.filter import DjangoFilterConnectionField

from .object_types import CommentObjectType


class CommentsQueries:
    comment = Node.Field(CommentObjectType)
    all_comments = DjangoFilterConnectionField(CommentObjectType)

    def resolve_all_comments(self, info, **kwargs):
        Comment = swapper.load_model("baseapp_comments", "Comment")
        app_label = Comment._meta.app_label

        if info.context.user.has_perm(f"{app_label}.view_all_comments"):
            return CommentObjectType._meta.model.objects.all()
        return CommentObjectType._meta.model.objects.none()
