import graphene
import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import IntegerField, OuterRef, Subquery, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce
from query_optimizer import DjangoConnectionField
from query_optimizer.prefetch_hack import evaluate_with_prefetch_hack

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
CommentableMetadata = swapper.load_model("baseapp_comments", "CommentableMetadata")
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

        if is_root_a_comment and (root.target_object_id or root.in_reply_to_id):
            qs = root.comments.filter(status=CommentStatus.PUBLISHED)
            if service := shared_services.get("blocks.lookup"):
                qs = service.exclude_blocked_from_foreign_queryset(qs, info)

            # The root.comments were already optimized. But because of the new filter, we need to
            # re-evaluate the queryset so it can be properly paginated.
            evaluate_with_prefetch_hack(qs)
            return qs

        qs = Comment.objects_visible.for_target(root, root_only=True)
        if service := shared_services.get("blocks.lookup"):
            qs = service.exclude_blocked_from_foreign_queryset(qs, info)

        if is_root_a_comment:
            # When the root is a comment used as a target, the AST walker can't handle the
            # nested comments -> comments structure with the regular info.  Stash a
            # NestedConnectionInfoProxy on the queryset hints so the patched
            # OptimizationCompilerPatch (in baseapp_core.graphql.optimizer) picks it up
            # when the DjangoConnectionField compiles the optimisation.  This avoids calling
            # optimize() eagerly, which would evaluate the queryset and break pagination.
            queryset_field_nodes = ConnectionFieldNodeExtractor(info).get_sliced_field_nodes()
            info_proxy = NestedConnectionInfoProxy(info, queryset_field_nodes=queryset_field_nodes)
            qs._hints[NESTED_INFO_PROXY_HINT] = info_proxy

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

    @classmethod
    def pre_optimization_hook(cls, queryset, optimizer):
        queryset = super().pre_optimization_hook(queryset, optimizer)

        # Required for CommentsInterface.resolve_comments checks (no longer a column).
        required_fields = [
            "id",
            "target_object_id",
            "in_reply_to_id",
            "status",
        ]
        optimizer.only_fields.extend(required_fields)
        if "comments" in optimizer.prefetch_related:
            required_fields_set = set(
                [*optimizer.prefetch_related["comments"].only_fields, "status"]
            )
            optimizer.prefetch_related["comments"].only_fields = list(required_fields_set)

        # Annotate commentable metadata for N+1 prevention (is_comments_enabled, comments_count).
        if service := shared_services.get("commentable_metadata"):
            queryset = service.annotate_queryset(queryset)

        # Annotation for replies_count_total ordering in CommentFilter.
        # JSON key lookup yields jsonb in PostgreSQL; cast to int so Coalesce with 0 is valid
        # and NULL (no metadata row) orders like 0.
        ct = ContentType.objects.get_for_model(Comment)
        replies_subquery = (
            CommentableMetadata.objects.filter(
                target__content_type=ct,
                target__object_id=OuterRef("pk"),
            )
            .annotate(
                _reply_total=Cast(
                    KeyTextTransform("total", "comments_count"),
                    output_field=IntegerField(),
                )
            )
            .values("_reply_total")[:1]
        )

        queryset = queryset.annotate(
            replies_count_total=Coalesce(
                Subquery(replies_subquery, output_field=IntegerField()),
                Value(0),
            ),
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
