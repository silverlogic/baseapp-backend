import dataclasses
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.db.models import QuerySet
from strawberry.types import Info
from strawberry_django.optimizer import OptimizerStore

from baseapp_core.strawberry import Node, django_type, type_for_model
from baseapp_core.strawberry.complexity import check_max_complexity
from baseapp_core.strawberry.fields import Languages, thumbnail_field

from ..models import AbstractPage, Metadata, URLPath

page_app_label = swapper.load_model("baseapp_pages", "Page")._meta.app_label

URLPathLazyType = type_for_model(URLPath)
MetadataLazyType = type_for_model(Metadata)


@dataclasses.dataclass
class MetadataValues:
    """Metadata computed for an object without a `Metadata` row (Graphene's
    `MetadataObjectType(...)` / `AbstractMetadataObjectType`). Unset fields resolve to null."""

    meta_title: str | None = None
    meta_description: str | None = None
    meta_robots: str | None = None
    meta_og_type: str | None = None
    meta_og_image: Any = None
    created: Any = None
    modified: Any = None
    target_object_id: int | None = None
    language: str | None = None
    pk: int | None = None


def _implementing_type(info: Info) -> Any:
    return getattr(info.schema.get_type_by_name(info._raw_info.parent_type.name), "origin", None)


@dataclasses.dataclass
class _MetadataOptimizerStore(OptimizerStore):
    """`only` hint of `metadata`, taken from the implementing type's `metadata_only` columns."""

    def __bool__(self) -> bool:
        return True

    def with_resolved_callables(self, info: Info) -> OptimizerStore:
        return OptimizerStore(only=list(getattr(_implementing_type(info), "metadata_only", ())))

    def with_prefix(self, prefix: str, *, info: Info) -> OptimizerStore:
        return self.with_resolved_callables(info).with_prefix(prefix, info=info)


@strawberry.interface(name="PageInterface")
class PageInterface(Node):
    """Implementing types provide `resolve_metadata(cls, root, info)` and, optionally, the
    `metadata_only` columns it reads."""

    @strawberry.field(graphql_type=Optional[URLPathLazyType])
    def url_path(self, info: Info) -> Any:
        return self.url_path

    @strawberry.field(graphql_type=Optional[list[Optional[URLPathLazyType]]])
    def url_paths(self, info: Info) -> Any:
        return self.url_paths.all()

    @strawberry.field(graphql_type=Optional[MetadataLazyType])
    def metadata(self, info: Info) -> Any:
        resolve = getattr(_implementing_type(info), "resolve_metadata", None)
        if resolve is None:
            raise NotImplementedError
        return resolve(self, info)


# The optimizer reads `store` from any field, not only strawberry-django ones.
PageInterface.__strawberry_definition__.get_field("metadata").store = _MetadataOptimizerStore()


# Defined with the interface so they are registered wherever PageInterface is used.
@django_type(URLPath)
class URLPathType(Node):
    created: strawberry.auto
    modified: strawberry.auto
    path: strawberry.auto
    language: Languages | None
    is_active: strawberry.auto
    pk: int | None = strawberry_django.field()

    @strawberry_django.field(
        graphql_type=Optional[PageInterface],
        only=["target_content_type_id", "target_object_id"],
    )
    def target(self, info: Info) -> Any:
        target = self.target
        if isinstance(target, AbstractPage) and not info.context.user.has_perm(
            f"{page_app_label}.view_page", target
        ):
            return None
        return target

    MAX_COMPLEXITY = 3

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        check_max_complexity(info, cls.MAX_COMPLEXITY)
        return queryset


@django_type(Metadata)
class MetadataType:
    created: strawberry.auto
    modified: strawberry.auto
    target_object_id: strawberry.auto
    language: Languages | None
    meta_title: strawberry.auto
    meta_description: strawberry.auto
    meta_robots: strawberry.auto
    meta_og_type: strawberry.auto
    meta_og_image: str | None = thumbnail_field("meta_og_image")
    pk: int | None = strawberry_django.field()

    @classmethod
    def is_type_of(cls, obj: Any, info: Info) -> bool:
        return isinstance(obj, (Metadata, MetadataValues))


def get_page_interface() -> type[PageInterface]:
    return PageInterface
