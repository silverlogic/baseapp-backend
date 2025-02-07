import swapper
from graphene_django.filter import DjangoFilterConnectionField

from baseapp_core.graphql import Node

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label
CommentObjectType = Comment.get_graphql_object_type()


class CommentsQueries:
    comment = Node.Field(CommentObjectType)
    all_comments = DjangoFilterConnectionField(CommentObjectType)

    def resolve_all_comments(self, info, **kwargs):
        if info.context.user.has_perm(f"{app_label}.view_all_comments"):
            return CommentObjectType._meta.model.objects.all()
        return CommentObjectType._meta.model.objects.none()
