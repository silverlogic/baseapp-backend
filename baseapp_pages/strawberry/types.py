from typing import Any

import strawberry
import strawberry_django
import swapper
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model, Q, QuerySet
from django.utils.translation import get_language
from strawberry.types import Info
from translated_fields import to_attribute

from baseapp_auth.strawberry.permissions import PermissionsInterface
from baseapp_core.plugins import strawberry_shared_interfaces
from baseapp_core.strawberry import Node, django_type, type_for_model
from baseapp_core.strawberry.complexity import check_max_complexity
from baseapp_core.strawberry.enums import enum_from_choices

from ..graphql.object_types import PageFilter
from ..models import Metadata
from .interfaces import MetadataValues, PageInterface

Page = swapper.load_model("baseapp_pages", "Page")
page_app_label = Page._meta.app_label

PageLazyType = type_for_model(Page)
PageStatusEnum = enum_from_choices(Page.PageStatus, "PageStatus")


def translated_columns(name: str) -> list[str]:
    """Columns `TranslatedField(name)` reads, for every configured language."""
    return [to_attribute(name, code) for code, _label in settings.LANGUAGES]


@strawberry_django.type(Page, name="AbstractPage")
class AbstractPageType:
    """Page fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto
    status: PageStatusEnum | None
    pk: int | None = strawberry_django.field()

    @strawberry_django.field(only=translated_columns("title"))
    def title(self, info: Info) -> str | None:
        return self.title

    @strawberry_django.field(only=translated_columns("body"))
    def body(self, info: Info) -> str | None:
        return self.body.html

    metadata_only = translated_columns("title")

    @classmethod
    def resolve_metadata(cls, root: Model, info: Info) -> Metadata | MetadataValues:
        metadata = Metadata.objects.filter(
            target_content_type=ContentType.objects.get_for_model(root),
            target_object_id=root.id,
            language=get_language(),
        ).first()
        if metadata:
            if not metadata.meta_title:
                metadata.meta_title = root.title
            return metadata
        return MetadataValues(meta_title=root.title)

    MAX_COMPLEXITY = 3

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        check_max_complexity(info, cls.MAX_COMPLEXITY)
        user = info.context.user
        if user.is_active and user.is_superuser:
            return queryset
        if not user.is_authenticated:
            return queryset.filter(status=Page.PageStatus.PUBLISHED)
        return queryset.filter(Q(status=Page.PageStatus.PUBLISHED) | Q(user=user))

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        node = super().get_node(info, pk)
        if not info.context.user.has_perm(f"{page_app_label}.view_page", node):
            return None
        return node


def page_interfaces() -> tuple[type, ...]:
    return (
        PageInterface,
        *strawberry_shared_interfaces.get("CommentsInterface"),
        PermissionsInterface,
        Node,
    )


# Columns read by the permission backend; deferred columns would be refetched per access.
@django_type(
    Page,
    filterset_class=PageFilter,
    relations=("user",),
    only=["status", "user_id"],
)
class PageType(AbstractPageType, *page_interfaces()):
    pass
