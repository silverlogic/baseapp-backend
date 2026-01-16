import graphene
import swapper
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from query_optimizer import DjangoConnectionField, optimize
from query_optimizer.prefetch_hack import evaluate_with_prefetch_hack

from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import ConnectionFieldNodeExtractor, DjangoObjectType
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import (
    ResolveInfoProxy,
    get_object_type_for_model,
    skip_ast_walker,
)
from baseapp_reactions.graphql.object_types import ReactionsInterface

from ..models import CommentStatus, default_comments_count
from .filters import CommentFilter

Comment = swapper.load_model("baseapp_comments", "Comment")
app_label = Comment._meta.app_label

CommentStatusEnum = graphene.Enum.from_enum(CommentStatus)


def create_object_type_from_dict(name, d):
    fields = {}
    for key_name in d.keys():
        fields[key_name] = graphene.Int(required=False)
    return type(name, (graphene.ObjectType,), fields)


CommentsCount = create_object_type_from_dict("CommentsCount", default_comments_count())


class CommentsInterface(RelayNode):
    comments_count = graphene.Field(CommentsCount, required=True)
    comments = DjangoConnectionField(get_object_type_for_model(Comment))
    is_comments_enabled = graphene.Boolean(required=True)

    class Meta:
        model = Comment

    def resolve_comments(root, info, **kwargs):
        # if root is a comment and is attached to a target use root.comments so it can be filtered
        # by using ForeignKey related field
        # if not then assume its another object type, like a post
        # this is used in the tests because we treat those comment as the target for other comments
        # so we can test the package without having to create a new model

        if not getattr(root, "is_comments_enabled", True):
            return skip_ast_walker(Comment.objects.none())

        CAN_ANONYMOUS_VIEW_COMMENTS = getattr(
            settings, "BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS", True
        )
        if not CAN_ANONYMOUS_VIEW_COMMENTS and not info.context.user.is_authenticated:
            return skip_ast_walker(Comment.objects.none())

        if isinstance(root, Comment) and (root.target_object_id or root.in_reply_to_id):
            qs = root.comments.filter(status=CommentStatus.PUBLISHED)
            # The root.comments were already optimized. But because of the new filter, we need to
            # re-evaluate the queryset so it can be properly paginated.
            evaluate_with_prefetch_hack(qs)
            return qs

        if root.__class__ == Comment:
            # When the root is a comment, we need to trick the optimizer to properly walk the AST.
            # The ast walker doesn't work properly with nested elements (comments -> comments).
            queryset_field_nodes = ConnectionFieldNodeExtractor(info).get_sliced_field_nodes()
            info_proxy = ResolveInfoProxy(info, queryset_field_nodes=queryset_field_nodes)
        else:
            info_proxy = info

        target_content_type = ContentType.objects.get_for_model(root)
        return optimize(
            Comment.objects_visible.filter(
                target_content_type=target_content_type,
                target_object_id=root.pk,
                in_reply_to__isnull=True,
            ),
            info_proxy,
        )


comment_interfaces = (
    RelayNode,
    CommentsInterface,
    ReactionsInterface,
    PermissionsInterface,
)

if apps.is_installed("baseapp.activity_log"):
    from baseapp.activity_log.graphql.interfaces import NodeActivityLogInterface

    comment_interfaces += (NodeActivityLogInterface,)


class BaseCommentObjectType:
    target = graphene.Field(CommentsInterface)
    status = graphene.Field(CommentStatusEnum)

    class Meta:
        interfaces = comment_interfaces
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
        if not info.context.user.has_perm(f"{app_label}.view_comment", node):
            return None
        return node

    @classmethod
    def pre_optimization_hook(cls, queryset, optimizer):
        queryset = super().pre_optimization_hook(queryset, optimizer)

        # Needed in the CommentsInterface.resolve_comments.
        required_fields = [
            "id",
            "target_object_id",
            "in_reply_to_id",
            "is_comments_enabled",
            "status",
        ]
        optimizer.only_fields.extend(required_fields)
        if "comments" in optimizer.prefetch_related:
            required_fields = [
                "status",
            ]
            required_fields_set = set(
                [*optimizer.prefetch_related["comments"].only_fields, *required_fields]
            )
            optimizer.prefetch_related["comments"].only_fields = list(required_fields_set)

        # In order to otimize custom filers from django_filters properly, we need to annotate them in the queryset.
        queryset = queryset.annotate(
            replies_count_total=models.F("comments_count__total"),
            reactions_count_total=models.F("reactions_count__total"),
        )
        return queryset

    @classmethod
    def get_queryset(cls, queryset, info):
        user = info.context.user
        if user.is_anonymous:
            return queryset

        profile = user.current_profile

        if not profile:
            return queryset

        bloked_profile_ids = profile.blocking.values_list("target_id", flat=True)
        bloker_profile_ids = profile.blockers.values_list("actor_id", flat=True)

        queryset = queryset.exclude(profile__id__in=bloked_profile_ids).exclude(
            profile__id__in=bloker_profile_ids
        )

        return queryset


class CommentObjectType(BaseCommentObjectType, DjangoObjectType):
    class Meta(BaseCommentObjectType.Meta):
        pass
