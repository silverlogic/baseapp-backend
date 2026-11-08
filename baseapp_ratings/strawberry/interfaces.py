from collections.abc import Callable, Iterable
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.apps import apps
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

from ..services import RatableMetadataService

RateModel = swapper.load_model("baseapp_ratings", "Rate")
RateLazyType = type_for_model(RateModel)


def _service() -> RatableMetadataService | None:
    return shared_services.get("ratable_metadata")


def _metadata_annotation(*names: str) -> dict[str, Callable[[Info], Any]]:
    """Optimizer hint: annotate metadata on whatever model implements the interface."""

    def annotation(name: str) -> Callable[[Info], Any]:
        return lambda info: _service().get_annotations(model_from_info(info))[name]

    return {name: annotation(name) for name in names}


def _rates_of(obj: Model) -> QuerySet:
    return RateModel.objects.filter(
        target_document__content_type=ContentType.objects.get_for_model(obj),
        target_document__object_id=obj.pk,
    )


def _my_rating(root: Model, info: Info, profile_id: strawberry.ID | None) -> Model | None:
    user = info.context.user
    if not user.is_authenticated:
        return None
    if not apps.is_installed("baseapp_profiles"):
        return _rates_of(root).filter(user=user).first()

    Profile = swapper.load_model("baseapp_profiles", "Profile")
    if profile_id:
        profile = Profile.objects.get_if_member(pk=get_pk_from_relay_id(profile_id), user=user)
    else:
        profile = user.current_profile
    if not profile:
        return None
    return _rates_of(root).filter(user=user, profile=profile).first()


@strawberry.interface(name="RatingsInterface")
class RatingsInterface(Node):
    """Ratings fields for any ratable model. Optimizer hints live on the fields themselves."""

    @strawberry_django.field(annotate=_metadata_annotation("_ratable_ratings_count"))
    def ratings_count(self, info: Info) -> int | None:
        service = _service()
        return service.get_ratings_count(self) if service else 0

    @strawberry_django.field(annotate=_metadata_annotation("_ratable_ratings_sum"))
    def ratings_sum(self, info: Info) -> int | None:
        service = _service()
        return service.get_ratings_sum(self) if service else 0

    @strawberry_django.field(annotate=_metadata_annotation("_ratable_ratings_average"))
    def ratings_average(self, info: Info) -> float | None:
        service = _service()
        return service.get_ratings_average(self) if service else 0.0

    @connection(
        CountedConnection[RateLazyType] | None,
        annotate=_metadata_annotation("_ratable_is_ratings_enabled"),
    )
    def ratings(self, info: Info) -> Iterable[Model]:
        service = _service()
        if service is not None and not service.is_ratings_enabled(self):
            return RateModel.objects.none()
        if not info.context.user.has_perm("baseapp_ratings.list_ratings"):
            return RateModel.objects.none()
        return _rates_of(self).order_by("-created")

    @strawberry_django.field(annotate=_metadata_annotation("_ratable_is_ratings_enabled"))
    def is_ratings_enabled(self, info: Info) -> bool:
        service = _service()
        return service.is_ratings_enabled(self) if service else True

    if apps.is_installed("baseapp_profiles"):

        @strawberry.field(graphql_type=Optional[RateLazyType])
        def my_rating(self, info: Info, profile_id: strawberry.ID | None = None) -> Any:
            return _my_rating(self, info, profile_id)

    else:

        @strawberry.field(graphql_type=Optional[RateLazyType])
        def my_rating(self, info: Info) -> Any:
            return _my_rating(self, info, None)
