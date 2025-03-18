import django_filters
import graphene
import swapper
from baseapp_auth.graphql import PermissionsInterface
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import get_language
from graphene import relay
from query_optimizer import optimize

from baseapp_comments.graphql.object_types import CommentsInterface
from baseapp_core.graphql import DjangoObjectType, LanguagesEnum, ThumbnailField
from baseapp_pages.models import AbstractPage, Metadata, URLPath

from ..meta import AbstractMetadataObjectType

Page = swapper.load_model("baseapp_pages", "Page")
page_app_label = Page._meta.app_label
PageStatusEnum = graphene.Enum.from_enum(Page.PageStatus)


class PageInterface(relay.Node):
    url_path = graphene.Field(lambda: URLPathNode)
    url_paths = graphene.List(lambda: URLPathNode)
    metadata = graphene.Field(lambda: MetadataObjectType)

    @classmethod
    def resolve_url_path(cls, instance, info, **kwargs):
        return instance.url_path

    @classmethod
    def resolve_url_paths(cls, instance, info, **kwargs):
        return instance.url_paths.all()
        # return URLPath.objects.filter(
        #     target_content_type=ContentType.objects.get_for_model(instance),
        #     target_object_id=instance.id,
        # )

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
        raise NotImplementedError


class URLPathNode(DjangoObjectType):
    target = graphene.Field(PageInterface)
    language = graphene.Field(LanguagesEnum)

    class Meta:
        interfaces = (relay.Node,)
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

    def resolve_target(self, info, **kwargs):
        if isinstance(self.target, AbstractPage):
            if not info.context.user.has_perm(f"{page_app_label}.view_page", self.target):
                return None
        return self.target

    @classmethod
    def get_queryset(cls, queryset, info):
        MAX_COMPLEXITY = 3
        return optimize(queryset, info, max_complexity=MAX_COMPLEXITY)


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
        interfaces = (relay.Node, PageInterface, PermissionsInterface, CommentsInterface)
        model = Page
        fields = ("pk", "user", "title", "body", "status", "created", "modified")
        filterset_class = PageFilter

    @classmethod
    def get_node(cls, info, id):
        node = super().get_node(info, id)
        if not info.context.user.has_perm(f"{page_app_label}.view_page", node):
            return None
        return node

    MAX_COMPLEXITY = 3

    @classmethod
    def get_queryset(cls, queryset, info):
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
    def resolve_body(cls, instance, info, **kwargs):
        return instance.body.html

    @classmethod
    def resolve_metadata(cls, instance, info, **kwargs):
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


class MetadataObjectType(DjangoObjectType):
    language = graphene.Field(LanguagesEnum)
    meta_og_image = ThumbnailField(required=False)

    class Meta:
        interfaces = []
        model = Metadata
        exclude = ("id",)

    @classmethod
    def is_type_of(cls, root, info):
        if isinstance(root, AbstractMetadataObjectType):
            return True
        return super().is_type_of(root, info)
