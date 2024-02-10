from baseapp_core.graphql import Node
from graphene_django.filter import DjangoFilterConnectionField

from .object_types import CommentObjectType


class CommentsQueries:
    comment = Node.Field(CommentObjectType)
    all_comments = DjangoFilterConnectionField(CommentObjectType)

    def resolve_all_comments(self, info, **kwargs):
        if info.context.user.has_perm("baseapp_comments.view_all_comments"):
            return CommentObjectType._meta.model.objects.all()
        return CommentObjectType._meta.model.objects.none()
