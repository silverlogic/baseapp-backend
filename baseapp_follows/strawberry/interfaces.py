from collections.abc import Callable, Iterable
from typing import Any

import strawberry
import strawberry_django
import swapper
from django.contrib.contenttypes.models import ContentType
from django.db.models import Model, QuerySet
from strawberry.types import Info

from baseapp_core.graphql import get_pk_from_relay_id
from baseapp_core.plugins import shared_services
from baseapp_core.strawberry import (
    CountedConnection,
    Node,
    model_from_info,
    type_for_model,
)
from baseapp_core.strawberry.connections import connection

from ..graphql.object_types import FollowsFilter
from ..services import FollowableMetadataService

Follow = swapper.load_model("baseapp_follows", "Follow")
Profile = swapper.load_model("baseapp_profiles", "Profile")
FollowLazyType = type_for_model(Follow)


def _service() -> FollowableMetadataService:
    if service := shared_services.get("followable_metadata"):
        return service
    raise RuntimeError("FollowableMetadata service is not available")


def _metadata_annotation(name: str) -> dict[str, Callable[[Info], Any]]:
    """Optimizer hint: annotate the count on whatever model implements the interface."""

    def annotation(info: Info) -> Any:
        return _service().get_annotations(model_from_info(info))[name]

    return {name: annotation}


def _follows_of(obj: Model, side: str) -> QuerySet:
    content_type = ContentType.objects.get_for_model(obj)
    return Follow.objects.filter(
        **{f"{side}__content_type": content_type, f"{side}__object_id": obj.pk}
    )


@strawberry.interface(name="FollowsInterface")
class FollowsInterface(Node):
    """Follows fields for any followable model. Optimizer hints live on the fields themselves."""

    @connection(CountedConnection[FollowLazyType] | None, filterset_class=FollowsFilter)
    def followers(self, info: Info) -> Iterable[Model]:
        return _follows_of(self, "target")

    @connection(CountedConnection[FollowLazyType] | None, filterset_class=FollowsFilter)
    def following(self, info: Info) -> Iterable[Model]:
        return _follows_of(self, "actor")

    @strawberry_django.field(annotate=_metadata_annotation("_followable_followers_count"))
    def followers_count(self, info: Info) -> int | None:
        return _service().get_followers_count(self)

    @strawberry_django.field(annotate=_metadata_annotation("_followable_following_count"))
    def following_count(self, info: Info) -> int | None:
        return _service().get_following_count(self)

    @strawberry.field
    def is_followed_by_me(self, info: Info, profile_id: strawberry.ID | None = None) -> bool | None:
        user = info.context.user
        if not user.is_authenticated:
            return False
        if profile_id:
            profile = Profile.objects.get_if_member(pk=get_pk_from_relay_id(profile_id), user=user)
        else:
            profile = user.current_profile
        if not profile:
            return False
        return Follow.is_following(profile, self)
