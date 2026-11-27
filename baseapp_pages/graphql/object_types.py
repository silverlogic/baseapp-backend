from typing import TYPE_CHECKING

import django_filters
import graphene
import swapper
from django.contrib.auth import get_permission_codename
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import get_language
from query_optimizer import optimize

from baseapp_auth.graphql import PermissionsInterface
from baseapp_core.graphql import DjangoObjectType, LanguagesEnum, ThumbnailField
from baseapp_core.graphql import Node as RelayNode
from baseapp_core.plugins import graphql_shared_interfaces, shared_services
from baseapp_pages.models import AbstractPage, Metadata, URLPath

if TYPE_CHECKING:
    from django.db.models import Model, QuerySet

Page = swapper.load_model("baseapp_pages", "Page")
page_app_label = Page._meta.app_label
PageStatusEnum = graphene.Enum.from_enum(Page.PageStatus)


# ================================
# URL Path Object Types/Interfaces
# ================================


def get_view_permission(target: "Model") -> str:
    """
    Name of the object-level permission that decides who may view a URL path's target.

    Pages keep `view_page` on the swapped Page model's app label; any other model uses
    Django's default `<app_label>.view_<model_name>`.
    """
    if isinstance(target, AbstractPage):
        return f"{page_app_label}.view_page"
    opts = target._meta
    return f"{opts.app_label}.{get_permission_codename('view', opts)}"


class PageInterface(RelayNode):
    url_path = graphene.Field(lambda: URLPathNode)
    url_paths = graphene.List(lambda: URLPathNode)
    metadata = graphene.Field(lambda: MetadataObjectType)

    @classmethod
    def resolve_url_path(cls, instance, info, **kwargs) -> URLPath | None:
        return instance.url_path

    @classmethod
    def resolve_url_paths(cls, instance, info, **kwargs) -> "QuerySet[URLPath]":
        return instance.url_paths.all()
        # return URLPath.objects.filter(
        #     target_content_type=ContentType.objects.get_for_model(instance),
        #     target_object_id=instance.id,
        # )

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs) -> "Metadata | MetadataObjectType":
        raise NotImplementedError


class URLPathNode(DjangoObjectType):
    target = graphene.Field(PageInterface)
    language = graphene.Field(LanguagesEnum)

    class Meta:
        interfaces = (RelayNode,)
        model = URLPath
        fields = (
            "id",
            "pk",
            "path",
            "language",
            "is_active",
            "created",
            "modified",
            "target",
        )
        filter_fields = {
            "id": ["exact"],
        }

    def resolve_target(self, info, **kwargs) -> "Model | None":
        """
        Return the target only when the requesting user may view it.

        `urlPath(path:)` reaches the target without going through its object type's
        `get_node`, so the object-level `view_<model>` permission that `get_node` relies on
        is checked here for every `PageInterface` model. A target whose model has no
        permission backend answering that permission is hidden.
        """
        target = self.target
        if target is None:
            return None
        if not info.context.user.has_perm(get_view_permission(target), target):
            return None
        return target

    @classmethod
    def get_queryset(cls, queryset, info) -> "QuerySet[URLPath]":
        MAX_COMPLEXITY = 3
        return optimize(queryset, info, max_complexity=MAX_COMPLEXITY)


# =====================
# Metadata Object Types
# =====================


class AbstractMetadataObjectType:
    def __init__(self, instance, info) -> None:
        self.instance = instance
        self.info = info


class MetadataObjectType(DjangoObjectType):
    language = graphene.Field(LanguagesEnum)
    meta_og_image = ThumbnailField(required=False)

    class Meta:
        interfaces = []
        model = Metadata
        exclude = ("id",)

    @classmethod
    def is_type_of(cls, root, info) -> bool:
        if isinstance(root, AbstractMetadataObjectType):
            return True
        return super().is_type_of(root, info)


# =================
# Page Object Types
# =================


class PageFilter(django_filters.FilterSet):
    class Meta:
        model = Page
        fields = ["status"]


class BasePageObjectType:
    metadata = graphene.Field(lambda: MetadataObjectType)
    status = graphene.Field(PageStatusEnum)
    title = graphene.String()
    body = graphene.String()

    class Meta:
        interfaces = graphql_shared_interfaces.get(
            RelayNode, PageInterface, PermissionsInterface, "CommentsInterface"
        )
        model = Page
        fields = ("pk", "user", "title", "body", "status", "created", "modified")
        filterset_class = PageFilter

    @classmethod
    def get_node(cls, info, id) -> AbstractPage | None:
        node = super().get_node(info, id)
        if not info.context.user.has_perm(f"{page_app_label}.view_page", node):
            return None
        return node

    MAX_COMPLEXITY = 3

    @classmethod
    def get_queryset(cls, queryset, info) -> "QuerySet[AbstractPage]":
        if info.context.user.is_active and info.context.user.is_superuser:
            return optimize(queryset, info, max_complexity=cls.MAX_COMPLEXITY)

        if not info.context.user.is_authenticated:
            return optimize(
                queryset.filter(status=Page.PageStatus.PUBLISHED),
                info,
                max_complexity=cls.MAX_COMPLEXITY,
            )
        else:
            return optimize(
                queryset.filter(Q(status=Page.PageStatus.PUBLISHED) | Q(user=info.context.user)),
                info,
                max_complexity=cls.MAX_COMPLEXITY,
            )

    @classmethod
    def pre_optimization_hook(cls, queryset, optimizer) -> "QuerySet[AbstractPage]":
        queryset = super().pre_optimization_hook(queryset, optimizer)
        if service := shared_services.get("commentable_metadata"):
            queryset = service.annotate_queryset(queryset)
        return queryset

    @classmethod
    def resolve_body(cls, instance, info, **kwargs) -> str:
        return instance.body.html

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs) -> Metadata | MetadataObjectType:
        target_content_type = ContentType.objects.get_for_model(instance)
        metadata = Metadata.objects.filter(
            target_content_type=target_content_type,
            target_object_id=instance.id,
            language=get_language(),
        ).first()
        if metadata:
            # set default meta_title
            if not metadata.meta_title:
                metadata.meta_title = instance.title

            return metadata
        return MetadataObjectType(
            meta_title=instance.title,
        )


class PageObjectType(BasePageObjectType, DjangoObjectType):
    class Meta(BasePageObjectType.Meta):
        pass
