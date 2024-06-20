import graphene
import swapper
from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType
from baseapp_reactions.graphql.object_types import ReactionsInterface
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from graphene import relay
from graphene_django.filter import DjangoFilterConnectionField

from ..models import CommentStatus, default_comments_count
from .filters import CommentFilter

Comment = swapper.load_model("baseapp_comments", "Comment")

CommentStatusEnum = graphene.Enum.from_enum(CommentStatus)


def create_object_type_from_dict(name, d):
    fields = {}
    for key_name in d.keys():
        fields[key_name] = graphene.Int(required=False)
    return type(name, (graphene.ObjectType,), fields)


CommentsCount = create_object_type_from_dict("CommentsCount", default_comments_count())


class CommentsInterface(relay.Node):
    comments_count = graphene.Field(CommentsCount, required=True)
    comments = DjangoFilterConnectionField(lambda: CommentObjectType)
    is_comments_enabled = graphene.Boolean(required=True)

    def resolve_comments(self, info, **kwargs):
        # if self is a comment and is attached to a target use self.comments so it can be filtered
        # by using ForeignKey related field
        # if not then assume its another object type, like a post
        # this is used in the tests because we treat those comment as the target for other comments
        # so we can test the package without having to create a new model

        if not getattr(self, "is_comments_enabled", True):
            return Comment.objects.none()

        CAN_ANONYMOUS_VIEW_COMMENTS = getattr(
            settings, "BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS", True
        )
        if not CAN_ANONYMOUS_VIEW_COMMENTS and not info.context.user.is_authenticated:
            return Comment.objects.none()

        if isinstance(self, Comment) and (self.target_object_id or self.in_reply_to_id):
            return self.comments.filter(status=CommentStatus.PUBLISHED)

        target_content_type = ContentType.objects.get_for_model(self)
        return Comment.objects_visible.filter(
            target_content_type=target_content_type,
            target_object_id=self.pk,
            in_reply_to__isnull=True,
        )


class CommentObjectType(DjangoObjectType):
    target = graphene.Field(CommentsInterface)
    status = graphene.Field(CommentStatusEnum)

    class Meta:
        interfaces = (relay.Node, CommentsInterface, ReactionsInterface, PermissionsInterface)
        model = Comment
        fields = (
            "pk",
            "user",
            "profile",
            "body",
            "created",
            "modified",
            "is_edited",
            "is_pinned",
            "target",
            "in_reply_to",
            "language",
            "status",
        )
        filterset_class = CommentFilter

    @classmethod
    def get_node(self, info, id):
        node = super().get_node(info, id)
        if not info.context.user.has_perm("baseapp_comments.view_comment", node):
            return None
        return node
