from collections.abc import Callable
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.db.models import Prefetch
from strawberry.types import Info
from strawberry_django.optimizer import optimize

from baseapp_core.graphql import resolve_document_content_object
from baseapp_core.models import DocumentId
from baseapp_core.strawberry import Node, django_type, type_for_model

from ..graphql.object_types import FollowsFilter

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")

FollowLazyType = type_for_model(Follow)


def _document_prefetch(attr: str) -> Callable[[Info], Prefetch]:
    """Optimizer hint: batch `attr` (a DocumentId FK) and its Profile `content_object`.

    The Profile queryset is optimized for the selection under the field (relay id, follows
    counts, ...). Other content types fall back to the request cache in
    `resolve_document_content_object`.
    """

    def prefetch(info: Info) -> Prefetch:
        profiles = optimize(Profile._default_manager.all(), info)
        documents = DocumentId.objects.select_related("content_type").prefetch_related(
            GenericPrefetch("content_object", [profiles])
        )
        return Prefetch(attr, queryset=documents)

    return prefetch


@strawberry_django.type(Follow, name="AbstractFollow")
class AbstractFollowType:
    """Follow fields, shared by the package type and project overrides."""

    created: strawberry.auto
    modified: strawberry.auto
    target_is_following_back: strawberry.auto

    @strawberry_django.field(
        graphql_type=Optional[Node],
        only=["actor_id"],
        prefetch_related=_document_prefetch("actor"),
    )
    def actor_object(self, info: Info) -> Any:
        return resolve_document_content_object(self.actor, info)

    @strawberry_django.field(
        graphql_type=Optional[Node],
        only=["target_id"],
        prefetch_related=_document_prefetch("target"),
    )
    def target_object(self, info: Info) -> Any:
        return resolve_document_content_object(self.target, info)


@django_type(Follow, filterset_class=FollowsFilter, relations=("user",))
class FollowType(AbstractFollowType, Node):
    pass
