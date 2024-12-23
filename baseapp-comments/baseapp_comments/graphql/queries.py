import swapper
from baseapp_core.graphql import Node, get_object_type_for_model
from graphene_django.filter import DjangoFilterConnectionField

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label
CommentObjectType = Comment.get_graphql_object_type()


class CommentsQueries:
    comment = Node.Field(get_object_type_for_model(Comment))
    all_comments = DjangoFilterConnectionField(get_object_type_for_model(Comment))

    def resolve_all_comments(self, info, **kwargs):
        if info.context.user.has_perm(f"{app_label}.view_all_comments"):
            return CommentObjectType._meta.model.objects.all()
        return CommentObjectType._meta.model.objects.none()
