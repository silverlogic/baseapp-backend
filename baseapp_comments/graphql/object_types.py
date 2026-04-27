import graphene
import swapper
from django.conf import settings
from django.db import models
from query_optimizer import DjangoConnectionField

from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import (
    ConnectionFieldNodeExtractor,
    DjangoObjectType,
    NestedConnectionInfoProxy,
)
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.graphql import get_object_type_for_model, skip_ast_walker
from baseapp_core.graphql.optimizer import NESTED_INFO_PROXY_HINT
from baseapp_core.plugins import (
    apply_if_installed,
    graphql_shared_interfaces,
    shared_services,
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

    def resolve_comments_count(root, info, **kwargs):
        if service := shared_services.get("commentable_metadata"):
            return service.get_comments_count(root)
        return default_comments_count()

    def resolve_is_comments_enabled(root, info, **kwargs):
        if service := shared_services.get("commentable_metadata"):
            return service.is_comments_enabled(root)
        return True

    def resolve_comments(root, info, **kwargs):
        # if root is a comment and is attached to a target use root.comments so it can be filtered
        # by using ForeignKey related field
        # if not then assume its another object type, like a post
        # this is used in the tests because we treat those comment as the target for other comments
        # so we can test the package without having to create a new model
        service = shared_services.get("commentable_metadata")
        if service and not service.is_comments_enabled(root):
            return skip_ast_walker(Comment.objects.none())

        CAN_ANONYMOUS_VIEW_COMMENTS = getattr(
            settings, "BASEAPP_COMMENTS_CAN_ANONYMOUS_VIEW_COMMENTS", True
        )
        if not CAN_ANONYMOUS_VIEW_COMMENTS and not info.context.user.is_authenticated:
            return skip_ast_walker(Comment.objects.none())

        is_root_a_comment = isinstance(root, Comment)
        if is_root_a_comment:
            qs = Comment.objects_visible.filter(
                models.Q(in_reply_to_id=root.id)
                | models.Q(
                    target_document__content_type__app_label=app_label,
                    target_document__content_type__model=Comment._meta.model_name,
                    target_document__object_id=root.id,
                    in_reply_to__isnull=True,
                )
            )

            # When the root is a comment used as a target, the AST walker can't handle the
            # nested comments -> comments structure with the regular info.  Stash a
            # NestedConnectionInfoProxy on the queryset hints so the patched
            # OptimizationCompilerPatch (in baseapp_core.graphql.optimizer) picks it up
            # when the DjangoConnectionField compiles the optimisation.  This avoids calling
            # optimize() eagerly, which would evaluate the queryset and break pagination.
            queryset_field_nodes = ConnectionFieldNodeExtractor(info).get_sliced_field_nodes()
            info_proxy = NestedConnectionInfoProxy(info, queryset_field_nodes=queryset_field_nodes)
            qs._hints[NESTED_INFO_PROXY_HINT] = info_proxy
        else:
            qs = Comment.objects_visible.for_target(root, root_only=True)

        if service := shared_services.get("blocks.lookup"):
            qs = service.exclude_blocked_from_foreign_queryset(qs, info)

        # Return the un-evaluated queryset so the DjangoConnectionField handles both
        # optimization and pagination (first/after slicing).
        return qs


class BaseCommentObjectType:
    target = graphene.Field(CommentsInterface)
    status = graphene.Field(CommentStatusEnum)

    class Meta:
        interfaces = graphql_shared_interfaces.get(
            RelayNode,
            CommentsInterface,
            ReactionsInterface,
            PermissionsInterface,
            "NodeActivityLogInterface",
        )
        model = Comment
        fields = (
            "pk",
            "user",
            *apply_if_installed("baseapp_profiles", ["profile"]),
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

    def resolve_target(root, info, **kwargs):
        if not root.target_document_id:
            return None

        request_cache = getattr(info.context, "_comment_target_cache", None)
        if request_cache is None:
            request_cache = {}
            setattr(info.context, "_comment_target_cache", request_cache)

        target_document = root.target_document
        cache_key = (target_document.content_type_id, target_document.object_id)
        if cache_key in request_cache:
            return request_cache[cache_key]

        model_cls = target_document.content_type.model_class()
        target = (
            model_cls.objects.filter(pk=target_document.object_id).first() if model_cls else None
        )
        request_cache[cache_key] = target
        return target

    @classmethod
    def pre_optimization_hook(cls, queryset, optimizer):
        queryset = super().pre_optimization_hook(queryset, optimizer)
        queryset = queryset.select_related("target_document", "target_document__content_type")

        # Required for CommentsInterface.resolve_comments checks (no longer a column).
        required_fields = [
            "id",
            "target_document_id",
            "in_reply_to_id",
            "status",
        ]
        optimizer.only_fields.extend(required_fields)
        if "comments" in optimizer.prefetch_related:
            required_fields_set = set(
                [*optimizer.prefetch_related["comments"].only_fields, "status"]
            )
            optimizer.prefetch_related["comments"].only_fields = list(required_fields_set)

        # Annotate commentable metadata (includes replies_count_total for CommentFilter).
        if service := shared_services.get("commentable_metadata"):
            queryset = service.annotate_queryset(queryset)

        queryset = queryset.annotate(
            reactions_count_total=models.F("reactions_count__total"),
        )
        return queryset

    @classmethod
    def get_queryset(cls, queryset, info):
        if service := shared_services.get("blocks.lookup"):
            return service.exclude_blocked_from_foreign_queryset(queryset, info)

        return queryset


class CommentObjectType(BaseCommentObjectType, DjangoObjectType):
    class Meta(BaseCommentObjectType.Meta):
        pass
