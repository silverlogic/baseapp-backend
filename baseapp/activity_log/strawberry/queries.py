from collections.abc import Iterable

import strawberry
from django.db.models import Model
from strawberry.types import Info

from ..models import ActivityLog
from .interfaces import activity_logs_connection
from .types import VisibilityTypesEnum


@strawberry.type
class ActivityLogQueries:
    @activity_logs_connection
    def activity_logs(
        self, info: Info, visibility: VisibilityTypesEnum | None = None
    ) -> Iterable[Model]:
        return ActivityLog.objects.all()
