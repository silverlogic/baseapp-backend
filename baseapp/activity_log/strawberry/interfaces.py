from collections.abc import Iterable
from typing import Any

import strawberry
from django.apps import apps
from django.db.models import Model
from strawberry.types import Info

from baseapp_core.strawberry import CountedConnection
from baseapp_core.strawberry.connections import connection

from ..filters import ActivityLogFilter
from ..models import ActivityLog
from .types import ActivityLogLazyType, VisibilityTypesEnum


def activity_logs_connection(resolver: Any) -> Any:
    """Activity log connection: `first: Int = 10`, at most 100 results, `ActivityLogFilter` args.

    `visibility` is accepted and ignored (kept for schema compatibility).
    """
    return connection(
        CountedConnection[ActivityLogLazyType] | None,
        filterset_class=ActivityLogFilter,
        default_first=10,
        max_results=100,
    )(resolver)


@strawberry.interface(name="NodeActivityLogInterface")
class NodeActivityLogInterface:
    @activity_logs_connection
    def node_activity_logs(
        self, info: Info, visibility: VisibilityTypesEnum | None = None
    ) -> Iterable[Model]:
        if not info.context.user.has_perm("activity_log.list_node_activitylog", self):
            return ActivityLog.objects.none()
        context_ids = self.pgh_event_model.objects.filter(pgh_obj_id=self.pk).values_list(
            "pgh_context_id", flat=True
        )
        return ActivityLog.objects.filter(pk__in=context_ids)


@strawberry.interface(name="UserActivityLogInterface")
class UserActivityLogInterface:
    @activity_logs_connection
    def activity_logs(
        self, info: Info, visibility: VisibilityTypesEnum | None = None
    ) -> Iterable[Model]:
        if not info.context.user.has_perm("activity_log.list_user_activitylog", self):
            return ActivityLog.objects.none()
        return ActivityLog.objects.filter(user_id=self.pk)


@strawberry.interface(name="ProfileActivityLogInterface")
class ProfileActivityLogInterface:
    @activity_logs_connection
    def activity_logs(
        self, info: Info, visibility: VisibilityTypesEnum | None = None
    ) -> Iterable[Model]:
        if not apps.is_installed("baseapp_profiles"):
            return ActivityLog.objects.none()
        if not info.context.user.has_perm("activity_log.list_profile_activitylog", self):
            return ActivityLog.objects.none()
        return ActivityLog.objects.filter(profile_id=self.pk)
