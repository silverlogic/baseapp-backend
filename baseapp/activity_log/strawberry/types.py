from collections.abc import Iterable
from datetime import datetime
from typing import Any, Optional

import strawberry
import strawberry_django
import swapper
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Model, Prefetch, QuerySet
from pghistory.models import MiddlewareEvents
from strawberry.types import Info
from strawberry_django.optimizer import optimize

from baseapp_core.strawberry import CountedConnection, Node, django_type, type_for_model
from baseapp_core.strawberry.connections import connection
from baseapp_core.strawberry.enums import enum_from_choices
from baseapp_core.strawberry.scalars import GenericScalar

from ..graphql.filters import ActivityLogFilter, MiddlewareEventFilter
from ..models import ActivityLog, VisibilityTypes

User = get_user_model()

ActivityLogLazyType = type_for_model(ActivityLog)
NodeLogEventLazyType = type_for_model(MiddlewareEvents)
UserLazyType = type_for_model(User)
VisibilityTypesEnum = enum_from_choices(VisibilityTypes, "VisibilityTypes")


def _prefetch_to_one(name: str, model: type[Model]) -> Any:
    # Prefetch, not select_related: the FK columns of the view may point at missing rows
    # (or be NULL), and an INNER JOIN would drop the activity log itself.
    def hint(info: Info) -> Prefetch:
        return Prefetch(name, queryset=optimize(model._default_manager.all(), info))

    return hint


def _related_or_none(instance: Model, name: str) -> Model | None:
    if getattr(instance, f"{name}_id") is None:
        return None
    try:
        return getattr(instance, name)
    except ObjectDoesNotExist:
        return None


@django_type(
    MiddlewareEvents,
    name="NodeLogEvent",
    filterset_class=MiddlewareEventFilter,
    relations=("user",),
)
class NodeLogEventType(Node):
    @strawberry_django.field(
        graphql_type=Optional[Node],
        description="The object of the event.",
        only=["pgh_obj_model", "pgh_obj_id"],
    )
    def obj(self, info: Info) -> Model | None:
        model = apps.get_model(self.pgh_obj_model)
        return model.objects.filter(pk=self.pgh_obj_id).first()

    label: str | None = strawberry_django.field(
        field_name="pgh_label", description="The event label."
    )

    @strawberry_django.field(description="The raw data of the event.", only=["pgh_data"])
    def data(self, info: Info) -> GenericScalar | None:
        if info.context.user.has_perm("activity_log.view_nodelogevent-data", self):
            return self.pgh_data
        return None

    @strawberry_django.field(
        description="The diff between the previous event of the same label.", only=["pgh_diff"]
    )
    def diff(self, info: Info) -> GenericScalar | None:
        if info.context.user.has_perm("activity_log.view_nodelogevent-diff", self):
            return self.pgh_diff
        return None

    created_at: datetime | None = strawberry_django.field(
        field_name="pgh_created_at", description="When the event was created."
    )


def activity_log_interfaces() -> tuple[type, ...]:
    if not apps.is_installed("baseapp_profiles"):
        return ()

    Profile = swapper.load_model("baseapp_profiles", "Profile")
    ProfileLazyType = type_for_model(Profile)

    @strawberry.interface(name="ActivityLogWithProfileInterface")
    class ActivityLogWithProfileInterface:
        @strawberry_django.field(
            only=["profile_id"], prefetch_related=[_prefetch_to_one("profile", Profile)]
        )
        def profile(self, info: Info) -> ProfileLazyType | None:
            return _related_or_none(self, "profile")

    return (ActivityLogWithProfileInterface,)


@strawberry_django.type(ActivityLog, name="AbstractActivityLog")
class AbstractActivityLogType:
    """ActivityLog fields, shared by the package type and project overrides."""

    created_at: strawberry.auto
    updated_at: strawberry.auto
    ip_address: str | None
    verb: str | None
    visibility: VisibilityTypesEnum | None
    url: str | None
    metadata: GenericScalar | None
    pk: int | None = strawberry_django.field()

    @strawberry_django.field(only=["user_id"], prefetch_related=[_prefetch_to_one("user", User)])
    def user(self, info: Info) -> UserLazyType | None:
        return _related_or_none(self, "user")

    @connection(
        CountedConnection[NodeLogEventLazyType] | None, filterset_class=MiddlewareEventFilter
    )
    def events(self, info: Info) -> Iterable[Model]:
        return MiddlewareEvents.objects.filter(pgh_context_id=self.pk)

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        if not info.context.user.has_perm("activity_log.list_activitylog_any_visibility"):
            queryset = queryset.filter(visibility=VisibilityTypes.PUBLIC)
        return queryset

    @classmethod
    def get_node(cls, info: Info, pk: Any) -> Model | None:
        # Like Graphene: the per-object permission only, without the visibility filter.
        obj = optimize(ActivityLog.objects.filter(pk=pk), info).first()
        if obj is None or not info.context.user.has_perm("activity_log.view_activitylog", obj):
            return None
        return obj


@django_type(ActivityLog, filterset_class=ActivityLogFilter)
class ActivityLogType(AbstractActivityLogType, *activity_log_interfaces(), Node):
    pass
